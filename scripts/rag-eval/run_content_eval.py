"""답변 내용 채점 평가 (RAG 설계서 5.3의 근거 판정 지표). ai-service 이미지에서 실행한다.

평가셋의 면접 답변마다 질문·답변으로 검색하고 score_content로 채점한다.
- 근거 상태 정확도: 판정한 근거 상태가 기대 상태와 같은 비율
- 근거 문장 정밀도: LLM이 고른 근거 문장 중 정답 문장의 비율
점수 오차는 사람이 매긴 기준 점수가 생기면 더한다.

필요한 것: postgres, embed-server, LLM 서버. 먼저 index_eval_posting.py로 공고를 색인한다.

final_project 폴더에서:
  docker run --rm --network pc1_default --env-file pc1/.env -e LLM_URL=<주소>/v1 -e LLM_MODEL=<모델> \
    -v "$(pwd)/ai-service:/src" -v "$(pwd)/scripts/rag-eval:/eval" -w /src pc2-ai-service:latest \
    python /eval/run_content_eval.py <공고 ID> <실험 ID>
"""

import json
import re
import statistics
import sys
import time
from pathlib import Path

sys.path[:0] = ["/src"]

from app.chains.answer_content import EvidenceStatus, judge_question_topic, score_content
from app.chains.structured import StructuredOutputError
from app.core.config import get_settings
from app.core.llm import get_chat_model
from app.prompts import answer_content as prompts
from app.rag.retriever import search_company_docs

# 평가셋 expect → 근거 상태. '낮은 일치'도 근거 상태는 근거 있음이다
EXPECTED = {
    "근거 있음": EvidenceStatus.FOUND,
    "근거 있음 (낮은 일치)": EvidenceStatus.FOUND,
    "㉠": EvidenceStatus.NO_QUESTION_DOC,
    "㉡": EvidenceStatus.NO_ANSWER_DOC,
    "무응답": EvidenceStatus.NO_CLAIM,
}
# 일치 단계 점수 (루브릭 설계서 3.2). '문서에 없음'은 ㉡의 50점이다
DOC_MATCH = {"같음": 100, "대부분 같음": 75, "일부만 같음": 25, "반대": 0, "문서에 없음": 50}


def reference_score(ref: dict, expect: str) -> float:
    """기준 점수로 내용 점수를 계산한다 (루브릭 설계서 3.3과 같은 식)."""
    if expect == "무응답":
        return 0.0
    if expect == "㉠":
        return (ref["relevance"] * 4 + ref["specificity"] * 3) / 7
    return (ref["relevance"] * 4 + ref["specificity"] * 3 + DOC_MATCH[ref["level"]] * 3) / 10


def _errors(result, ref: dict, expect: str) -> dict:
    """LLM 점수와 기준 점수의 차이. 일치 축은 둘 다 일치 단계가 있을 때만 잰다."""
    read = result.llm_output["read"]
    ref_level = ref["level"] if expect not in ("㉠", "무응답") else None
    both = ref_level is not None and result.doc_match_level is not None
    return {
        "reference_score": round(reference_score(ref, expect), 2),
        "score_error": round(abs(float(result.score) - reference_score(ref, expect)), 2),
        "relevance_error": abs(read["relevance"] - ref["relevance"]),
        "specificity_error": abs(read["specificity"] - ref["specificity"]),
        "doc_match_error": abs(DOC_MATCH[result.doc_match_level] - DOC_MATCH[ref_level]) if both else None,
        "level": result.doc_match_level,
        "reference_level": ref_level,
        "level_ok": result.doc_match_level == ref_level if ref_level else None,
        "human_reviewed": ref["human_reviewed"],
    }
# 평가셋에 없는 공고라 직무 설명을 여기 둔다
JOB_DESCRIPTION = (
    "사내 기술문서 질의응답 RAG 서비스를 개발·운영한다. "
    "문서 색인 파이프라인, 검색 품질 개선, LangGraph 에이전트 구현을 맡는다."
)


class TimedModel:
    """LLM 호출마다 걸린 시간과 토큰 수를 남긴다. 캐시 토큰은 Ollama가 앞부분 계산을 다시 쓴 양이다."""

    def __init__(self, model):
        self.model = model
        self.calls: list[dict] = []

    def invoke(self, messages):
        started = time.perf_counter()
        out = self.model.invoke(messages)
        usage = getattr(out, "usage_metadata", None) or {}
        self.calls.append({
            "kind": _call_kind(messages[-1].content),
            "seconds": round(time.perf_counter() - started, 2),
            "input_tokens": usage.get("input_tokens"),
            "cached_tokens": (usage.get("input_token_details") or {}).get("cache_read"),
            "output_tokens": usage.get("output_tokens"),
        })
        return out


def _call_kind(last_message: str) -> str:
    if "[지원자가 말한 것]" in last_message:
        return "주장"
    if "question_in_docs" in last_message:
        return "주제"
    if "[지원자 답변]" in last_message:
        return "읽기"
    return "재시도"  # 형식 오류나 빈 주장으로 다시 물은 요청


def _call_text(c: dict) -> str:
    cached = f", 캐시 {c['cached_tokens']}" if c["cached_tokens"] else ""
    return f"{c['kind']} {c['seconds']}s(입력 {c['input_tokens']}{cached})"


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _is_gold(sentence: str, gold: list[str]) -> bool:
    """문장 분리 방식이 달라 정답 문장 하나가 근거 문장 여러 개로 나뉘거나 그 반대일 수 있다."""
    s = _norm(sentence)
    return any(s in _norm(g) or _norm(g) in s for g in gold)


def evaluate(posting_id: int) -> list[dict]:
    queries = json.loads(Path("/eval/rag_eval_set.json").read_text(encoding="utf-8"))["queries"]
    by_id = {q["id"]: q for q in queries}
    rows = []
    for a in (q for q in queries if q["kind"] == "면접 답변"):
        q = by_id[a["question"]]
        question_context = search_company_docs(posting_id, [q["query"]])
        answer_context = search_company_docs(posting_id, [a["query"]])
        model = TimedModel(get_chat_model())
        prepare_seconds = 0.0
        started = time.perf_counter()
        try:
            # 실제 면접처럼 질문을 낼 때 질문 주제를 판정해 둔다. 지원자가 기다리는 시간이 아니므로 채점 시간에서 뺀다
            topic = judge_question_topic(q["query"], question_context, model=model)
            for c in model.calls:
                c["kind"] = "출제 때 " + c["kind"]
            prepare_seconds = round(time.perf_counter() - started, 1)
            started = time.perf_counter()
            result = score_content(
                q["query"], a["query"], question_context, answer_context, JOB_DESCRIPTION, model=model, topic=topic
            )
        except StructuredOutputError as e:
            # 재시도해도 형식 검증에 실패했다. 이 답변은 틀린 것으로 세고 다음으로 넘어간다 (검증 실패율)
            seconds = time.perf_counter() - started
            rows.append({"id": a["id"], "expect": a["expect"], "status": "형식 실패", "status_ok": False,
                         "format_failed": True, "error": str(e), "evidence": [], "evidence_gold": [],
                         "seconds": round(seconds, 1), "calls": model.calls})
            print(f"{a['id']:<3} X 기대={a['expect']:<14} 결과=형식 실패 ({seconds:.1f}s)\n      {str(e)[:150]}", flush=True)
            continue
        seconds = time.perf_counter() - started
        expected = EXPECTED[a["expect"]]
        rows.append(
            {
                "id": a["id"],
                "expect": a["expect"],
                "status": result.status.value,
                "status_ok": result.status == expected,
                "score": str(result.score),
                "evidence": [e.sentence for e in result.evidence],
                "evidence_gold": [_is_gold(e.sentence, a["gold"]) for e in result.evidence],
                "reason": result.reason,
                # LLM이 낸 값 그대로 {"read": 답변 읽기, "topic": 질문 주제, "claims": 주장별 비교}. 점수 계산 전 값이다
                "llm": result.llm_output,
                "question_context": len(question_context),
                "answer_context": len(answer_context),
                "seconds": round(seconds, 1),
                "prepare_seconds": prepare_seconds,
                "calls": model.calls,
                **(_errors(result, a["reference"], a["expect"]) if "reference" in a else {}),
            }
        )
        r = rows[-1]
        mark = "O" if r["status_ok"] else "X"
        read, topic, judged = r["llm"]["read"], r["llm"]["topic"], r["llm"]["claims"]
        print(f"{r['id']:<3} {mark} 기대={r['expect']:<14} 결과={r['status']:<8} 점수={r['score']:>6} "
              f"근거 {sum(r['evidence_gold'])}/{len(r['evidence'])} 정답 (답변 뒤 {r['seconds']}s, 출제 때 {prepare_seconds}s)\n"
              f"      읽기: 적합 {read['relevance']} 구체 {read['specificity']} | "
              f"주제: {topic['question_in_docs'] if topic else '문서 없음'}", flush=True)
        for i, claim in enumerate(read["claims"]):
            j = judged[i] if i < len(judged) else None
            print(f"         {i + 1}. {claim[:60]} → {j['level'] + ' ' + str(j['evidence_ids']) if j else '-'}", flush=True)
        print("      호출: " + " | ".join(_call_text(c) for c in model.calls), flush=True)
        if "reference_score" in r:
            print(f"      기준: {r['reference_score']}점 (차이 {r['score_error']}) | 단계 LLM {r['level']} / 기준 {r['reference_level']}", flush=True)
    return rows


def report(rows: list[dict]) -> dict:
    status_accuracy = sum(r["status_ok"] for r in rows) / len(rows)
    picked = [ok for r in rows for ok in r["evidence_gold"]]
    precision = sum(picked) / len(picked) if picked else None
    print(f"\n근거 상태 정확도 {status_accuracy:.1%} ({sum(r['status_ok'] for r in rows)}/{len(rows)})")
    print(f"근거 문장 정밀도 {precision:.1%} ({sum(picked)}/{len(picked)})" if picked else "근거 문장 없음")
    scored = [r for r in rows if "score_error" in r]
    errors = {}
    if scored:
        for key, label in (("score_error", "점수 오차"), ("relevance_error", "  적합성 오차"),
                           ("specificity_error", "  구체성 오차"), ("doc_match_error", "  일치 오차")):
            values = [r[key] for r in scored if r[key] is not None]
            errors[key] = statistics.mean(values) if values else None
            print(f"{label} 평균 {errors[key]:.1f}점 ({len(values)}개)" if values else f"{label} 없음")
        judged = [r["level_ok"] for r in scored if r["level_ok"] is not None]
        errors["level_agreement"] = sum(judged) / len(judged) if judged else None
        print(f"일치 단계 일치율 {errors['level_agreement']:.1%} ({sum(judged)}/{len(judged)})" if judged else "일치 단계 비교 없음")
    failed = sum(r.get("format_failed", False) for r in rows)
    print(f"검증 실패율 {failed / len(rows):.1%} ({failed}/{len(rows)}, 재시도해도 형식이 맞지 않은 답변)")
    print(f"채점 시간(답변 뒤 대기) 중앙 {statistics.median(r['seconds'] for r in rows):.1f}s")
    calls = [c for r in rows for c in r.get("calls", [])]
    by_kind = {}
    for kind in ("출제 때 주제", "읽기", "주제", "주장", "재시도"):
        seconds = [c["seconds"] for c in calls if c["kind"] == kind]
        if seconds:
            cached = [c["cached_tokens"] or 0 for c in calls if c["kind"] == kind]
            by_kind[kind] = {"count": len(seconds), "median_seconds": statistics.median(seconds),
                             "median_cached_tokens": statistics.median(cached)}
            print(f"  {kind}: {len(seconds)}번, 중앙 {statistics.median(seconds):.1f}s, 캐시 토큰 중앙 {statistics.median(cached):.0f}")
    return {
        **errors,
        "calls_by_kind": by_kind,
        "status_accuracy": status_accuracy,
        "evidence_precision": precision,
        "format_failure_rate": failed / len(rows),
        "median_seconds": statistics.median(r["seconds"] for r in rows),
    }


if __name__ == "__main__":
    posting_id, experiment = int(sys.argv[1]), sys.argv[2]
    rows = evaluate(posting_id)
    summary = report(rows)
    settings = get_settings()
    out = Path("/eval/results") / f"content-{experiment}.json"
    out.write_text(
        json.dumps(
            {"experiment": experiment, "posting_id": posting_id, "prompt_version": prompts.VERSION,
             "llm_model": settings.LLM_MODEL, "summary": summary, "rows": rows},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"저장: {out}")
