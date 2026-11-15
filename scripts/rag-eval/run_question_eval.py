"""면접 질문 생성 평가 (SYS-006, AI Agent 설계서 3장). ai-service 이미지에서 실행한다.

document_eval_set.json의 지원자마다 질문 생성 그래프를 실제 LLM으로 돌리고, 질문마다 아래를 남긴다.
- 경로: 통과(몇 번째 시도) / fallback / template
- 검증 실패 원인과 feedback, 검색어 수정 결과
- 시간: 질문마다, 지원자마다

질문 품질은 사람이 본다. results/question-<실험 ID>-review.csv에 질문마다 적절성·겹침 판정 칸을 둔다.

필요한 것: postgres, embed-server, LLM 서버. 공고는 index_eval_posting.py로 색인한 것을 쓴다 (평가 공고 3479).

PC2의 final_project 폴더에서 (PowerShell, pc2/.env에 DB·embed-server·LLM 주소가 있다):
  docker run --rm --env-file pc2/.env -v "${PWD}/ai-service:/src" -v "${PWD}/scripts/rag-eval:/eval" -w /src pc2-ai-service:latest python /eval/run_question_eval.py <공고 ID> <실험 ID> [직무 수] [인성 수]
"""

import csv
import json
import sys
import time
from pathlib import Path

sys.path[:0] = ["/src"]

from app.core.llm import get_chat_model
from app.graphs.question import _STEPS_PER_QUESTION, build_queries, build_question_graph, essays_text
from app.prompts import question as prompts
from app.rag.retriever import search_company_docs
from app.schemas.internal import ApplicantDocuments, PostingBrief

EVAL = json.loads(Path("/eval/document_eval_set.json").read_text(encoding="utf-8"))
START_NODES = {"next_job", "next_personality"}


def run_applicant(graph, posting: PostingBrief, documents: ApplicantDocuments, job_count: int, personality_count: int):
    """그래프를 stream으로 돌려 질문마다 거친 노드를 모은다."""
    state = {"posting": posting, "documents": documents, "essays": essays_text(documents),
             "queries": build_queries(documents, job_count), "personality_count": personality_count,
             "idx": 0, "confirmed": [], "job": [], "personality": []}
    questions, cur, last = [], None, time.perf_counter()
    for event in graph.stream(state, {"recursion_limit": _STEPS_PER_QUESTION * (job_count + personality_count) + 10},
                              stream_mode="updates"):
        (node, update), = event.items()
        now = time.perf_counter()
        if node in START_NODES:
            cur = {"type": update["question_type"], "query": update.get("query"), "steps": [], "seconds": 0.0}
            questions.append(cur)
        if cur is None:
            continue
        cur["seconds"] = round(cur["seconds"] + now - last, 1)
        step = {"node": node, "seconds": round(now - last, 1)}
        update = update or {}
        for key in ("question", "based_on", "failure_type", "feedback", "retry_count", "query"):
            if key in update and node not in START_NODES:
                step[key] = update[key]
        cur["steps"].append(step)
        if node == "append":
            cur["question"] = (update.get("job") or update.get("personality"))[-1]
            cur["based_on"] = next((s["based_on"] for s in reversed(cur["steps"]) if s.get("based_on")), "")
            nodes = [s["node"] for s in cur["steps"]]
            cur["path"] = "template" if "template" in nodes else (
                "fallback" if {"fallback", "fallback_personality"} & set(nodes) else "통과")
            cur["attempts"] = sum(n in ("validate", "validate_personality") for n in nodes)
        last = now
    return questions


def main(posting_id: int, experiment: str, job_count: int, personality_count: int) -> None:
    posting = PostingBrief(posting_id=posting_id, **EVAL["posting"])
    graph = build_question_graph(get_chat_model(), lambda q: [c.content for c in search_company_docs(posting_id, [q])])
    results = []
    for a in EVAL["applicants"]:
        started = time.perf_counter()
        questions = run_applicant(graph, posting, ApplicantDocuments(**a["documents"]), job_count, personality_count)
        seconds = round(time.perf_counter() - started, 1)
        results.append({"applicant": a["id"], "seconds": seconds, "questions": questions})
        paths = [q.get("path") for q in questions]
        print(f"{a['id']}: {seconds}초, 질문 {len(questions)}개, 경로 {paths}", flush=True)

    all_q = [q for r in results for q in r["questions"]]
    summary = {
        "질문 수": len(all_q),
        "경로": {p: sum(q.get("path") == p for q in all_q) for p in ("통과", "fallback", "template")},
        "첫 시도 통과": sum(q.get("path") == "통과" and q.get("attempts") == 1 for q in all_q),
        "실패 원인": {t: sum(s.get("failure_type") == t for q in all_q for s in q["steps"])
                   for t in ("evidence", "question", "overlap")},
        "지원자당 시간(초)": [r["seconds"] for r in results],
        "질문당 시간 중앙(초)": sorted(q["seconds"] for q in all_q)[len(all_q) // 2] if all_q else None,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))

    out = Path(f"/eval/results/question-{experiment}.json")
    out.write_text(json.dumps({"experiment": experiment, "posting_id": posting_id, "prompt_version": prompts.VERSION,
                               "job_count": job_count, "personality_count": personality_count,
                               "summary": summary, "results": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    review = Path(f"/eval/results/question-{experiment}-review.csv")
    with review.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["지원자", "순번", "유형", "경로", "검증 횟수", "검색어(앞 80자)", "질문",
                    "바탕 문장(based_on, 통과한 질문만)", "[판정] 적절 (맞음/애매/틀림)", "[판정] 같은 지원자의 다른 질문과 겹침 (예/아니오)", "[메모]"])
        for r in results:
            for i, q in enumerate(r["questions"], start=1):
                w.writerow([r["applicant"], i, q["type"], q.get("path"), q.get("attempts"),
                            (q.get("query") or "").replace("\n", " ")[:80], q.get("question"),
                            q.get("based_on", "") if q.get("path") == "통과" else "", "", "", ""])
    print(f"저장: {out.name}, {review.name}")


if __name__ == "__main__":
    args = sys.argv[1:]
    main(int(args[0]), args[1], int(args[2]) if len(args) > 2 else 3, int(args[3]) if len(args) > 3 else 2)
