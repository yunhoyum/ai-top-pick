"""꼬리질문 생성 평가 (SYS-008, AI Agent 설계서 5장). ai-service 이미지에서 실행한다.

rag_eval_set.json의 면접 답변 중 기준 점수가 80 이상인 답변(실제로 꼬리질문이 만들어지는 경우)마다
꼬리질문 서브그래프를 실제 LLM으로 돌리고 아래를 남긴다.
- 경로: 통과(몇 번째 생성) / fallback / 없음
- 검증 실패 feedback, 에러 수
- 시간: 노드마다, 답변마다 (지원자가 기다리는 시간이다)
- 자동 표시: 프롬프트 말이 새어 나옴('직전 답변' 등), 형식 위반
꼬리질문 품질은 사람이 본다. results/followup-<실험 ID>-review.csv에 판정 칸을 둔다.

입력은 실제 면접과 같게 만든다. 회사 문서는 질문·답변 검색 결과, 비교 대상은 평가셋의 다른 질문이다.

PC2의 final_project 폴더에서 (PowerShell):
  docker run --rm --env-file pc2/.env -v "${PWD}/ai-service:/src" -v "${PWD}/scripts/rag-eval:/eval" -w /src pc2-ai-service:latest python /eval/run_follow_up_eval.py <공고 ID> <실험 ID>
"""

import csv
import json
import re
import statistics
import sys
import time
from pathlib import Path

sys.path[:0] = ["/src"]

from app.core.llm import get_chat_model
from app.graphs.interview.follow_up_nodes import RECURSION_LIMIT, build_follow_up_graph
from app.graphs.question import form_problem
from app.prompts import follow_up as prompts
from app.rag.retriever import search_company_docs

EVAL = json.loads(Path("/eval/rag_eval_set.json").read_text(encoding="utf-8"))
DOC_MATCH = {"같음": 100, "대부분 같음": 75, "일부만 같음": 25, "반대": 0, "문서에 없음": 50}
MIN_SCORE = 80  # 꼬리질문 조건 (SYS-008). 기준 점수로 고른다
# 프롬프트에서 쓰는 이름표가 질문에 새어 나온 것
_LEAK = re.compile(r"직전 답변|직전 질문|처음 질문|이미 나온 질문|\[")


def reference_score(ref: dict) -> float:
    """기준 내용 점수 (루브릭 설계서 3.3). 근거 있음·㉡만 고르므로 세 축 식이다."""
    return (ref["relevance"] * 4 + ref["specificity"] * 3 + DOC_MATCH[ref["level"]] * 3) / 10


def targets() -> list[tuple[dict, dict]]:
    queries = EVAL["queries"]
    by_id = {q["id"]: q for q in queries}
    picked = []
    for a in queries:
        ref = a.get("reference")
        if a["kind"] != "면접 답변" or not ref or ref.get("memo", "").startswith("[동떨어진 답변]"):
            continue
        if a["expect"] in ("근거 있음", "㉡") and reference_score(ref) >= MIN_SCORE:
            picked.append((by_id[a["question"]], a))
    return picked


def run(graph, inputs: dict) -> dict:
    steps, last = [], time.perf_counter()
    final: dict = {}
    for event in graph.stream(inputs, {"recursion_limit": RECURSION_LIMIT}, stream_mode="updates"):
        (node, update), = event.items()
        now = time.perf_counter()
        update = update or {}
        step = {"node": node, "seconds": round(now - last, 1)}
        for key in ("follow_up", "valid", "feedback", "retry_count", "error_count", "errored"):
            if key in update:
                step[key] = update[key]
        steps.append(step)
        final |= update
        last = now
    generated = sum(s["node"] == "generate_follow_up" for s in steps)
    if not final.get("valid"):
        path = "없음"
    elif steps[-1]["node"] == "fallback_follow_up":
        path = "fallback"
    else:
        path = f"통과 ({generated}번째 생성)"
    return {"follow_up": final.get("follow_up") if final.get("valid") else None, "path": path, "steps": steps,
            "seconds": round(sum(s["seconds"] for s in steps), 1)}


def main(posting_id: int, experiment: str) -> None:
    model = get_chat_model()
    graph = build_follow_up_graph(model)
    main_questions = [q for q in EVAL["queries"] if q["kind"] == "면접 질문"]
    rows = []
    for q, a in targets():
        contexts = [c.content for c in search_company_docs(posting_id, [q["query"]]) +
                    search_company_docs(posting_id, [a["query"]])]
        inputs = {
            "prev_question": q["query"], "prev_answer": a["query"], "parent_question": q["query"],
            "contexts": list(dict.fromkeys(contexts)),
            "compare_questions": [m["query"] for m in main_questions if m["id"] != q["id"]],
        }
        r = run(graph, inputs)
        fu = r["follow_up"] or ""
        r |= {"id": a["id"], "question_id": q["id"], "question": q["query"], "answer": a["query"],
              "leak": bool(fu and _LEAK.search(fu)), "form_problem": form_problem(fu) if fu else None}
        rows.append(r)
        flags = (" [새어 나옴]" if r["leak"] else "") + (f" [형식: {r['form_problem']}]" if r["form_problem"] else "")
        print(f"{a['id']:<4} {r['path']:<14} {r['seconds']:>5}s{flags}\n      {fu or '-'}", flush=True)
        for s in r["steps"]:
            if s["node"] == "validate_follow_up" and s.get("feedback"):
                print(f"      검증 실패: {s['feedback']}", flush=True)

    made = [r for r in rows if r["follow_up"]]
    summary = {
        "count": len(rows),
        "made": len(made),
        "passed_first": sum(r["path"] == "통과 (1번째 생성)" for r in rows),
        "fallback": sum(r["path"] == "fallback" for r in rows),
        "none": sum(r["path"] == "없음" for r in rows),
        "leak": sum(r["leak"] for r in rows),
        "median_seconds": statistics.median(r["seconds"] for r in rows),
        "max_seconds": max(r["seconds"] for r in rows),
        "median_generations": statistics.median(sum(s["node"] == "generate_follow_up" for s in r["steps"]) for r in rows),
    }
    print(f"\n답변 {summary['count']}개: 꼬리질문 {summary['made']} (첫 생성 통과 {summary['passed_first']}, "
          f"fallback {summary['fallback']}), 없음 {summary['none']}, 새어 나옴 {summary['leak']}")
    print(f"시간 중앙 {summary['median_seconds']}s, 최대 {summary['max_seconds']}s, 생성 횟수 중앙 {summary['median_generations']}")

    out = Path(f"/eval/results/followup-{experiment}.json")
    out.write_text(json.dumps({"experiment": experiment, "posting_id": posting_id, "prompt_version": prompts.VERSION,
                               "summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    review = Path(f"/eval/results/followup-{experiment}-review.csv")
    with review.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["답변 ID", "면접 질문", "지원자 답변", "꼬리질문", "경로", "자동: 새어 나옴",
                    "[판정] 답변에서 한 말을 이어 묻나 (예/아니오)", "[판정] 하지 않은 일을 전제하나 (예/아니오)",
                    "[판정] 다른 질문과 겹치나 (예/아니오)", "[판정] 메모"])
        for r in rows:
            w.writerow([r["id"], r["question"], r["answer"], r["follow_up"] or "", r["path"],
                        "예" if r["leak"] else "", "", "", "", ""])
    print(f"저장: {out.name}, {review.name}")


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2])
