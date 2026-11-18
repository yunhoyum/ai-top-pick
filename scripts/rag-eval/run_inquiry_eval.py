"""기술 문의 분석 평가 (SYS-003, AI Agent 설계서 2.3 T-21·T-22). ai-service 이미지에서 실행한다.

inquiry_eval_set.json의 문의마다 결함 분석(analyze)을 실제 LLM으로 돌리고 아래를 잰다. 한 번에 여러 프롬프트 버전을 비교한다.
- 원인 정답률: cause가 정답과 같은가 (시스템 측 / 지원자 측 / 원인 판단 불가)
- 재검사 정답률: system_checkable이 정답과 같은가. 틀리면 해결 확인이 잘못된 방법으로 간다
- 안내 적중률: reply에 그 문제에 맞는 말(keywords)이 하나라도 있는가. 없으면 엉뚱한 안내로 본다
- 다시 시도: tried가 있는 문의에서 solution이 앞의 방법과 거의 같은가 (difflib 0.8 이상)
- 금지어: forbidden이 있는 문의(시스템 측)에서 reply·solution에 그 말(새로고침, 다시 접속 등)이 있는가 (평가 세트 v2)
- 반복 일치율: 같은 문의를 여러 번 돌렸을 때 원인이 모두 같은 문의의 비율 (통합테스트에서 판정이 흔들림)
- 형식 실패(재시도해도 JSON 검증 실패), 시간
안내 문구 품질은 사람이 본다. results/inquiry-<실험 ID>-review.csv에 판정 칸을 둔다.

버전: frozen/inquiry_<버전>.py는 앱에서 바꾸기 전 사본, 그 밖은 앱의 app/prompts/inquiry.py(지금 버전).
비교 대상은 FROZEN에 적는다 (실험 I3부터 v3 사본과 비교).

PC2의 final_project 폴더에서 (PowerShell):
  docker run --rm --env-file pc2/.env -v "${PWD}/ai-service:/src" -v "${PWD}/scripts/rag-eval:/eval" -w /src pc2-ai-service:latest python /eval/run_inquiry_eval.py <실험 ID> [반복 횟수] [current]
  (current를 주면 사본은 빼고 지금 버전만 돌린다)
"""

import csv
import difflib
import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path

sys.path[:0] = ["/src"]

from app.chains.structured import invoke_structured
from app.core.llm import get_chat_model
from app.prompts import inquiry as current
from app.schemas.llm_outputs import InquiryAnalysis

EVAL = json.loads(Path("/eval/inquiry_eval_set.json").read_text(encoding="utf-8"))
GREETING = current.GREETING


FROZEN = "v3"


def frozen(version: str):
    spec = importlib.util.spec_from_file_location(f"inquiry_{version}", f"/eval/frozen/inquiry_{version}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inputs(case: dict) -> tuple[list[dict], list[dict], list[str]]:
    """실제 문의와 같은 입력: 인사말 → 지원자 메시지 (다시 시도면 앞의 안내까지), 로그는 1초 간격 시각."""
    messages = [{"speaker": "챗봇", "text": GREETING}, {"speaker": "지원자", "text": case["message"]}]
    for t in case.get("tried", []):
        messages += [{"speaker": "챗봇", "text": t}]
    logs = [{"logged_at": f"2026-11-16T10:00:{i:02d}+09:00", "content": c} for i, c in enumerate(case["logs"])]
    return messages, logs, case.get("tried", [])


def run_case(model, prompts, case: dict) -> dict:
    messages, logs, tried = inputs(case)
    start = time.perf_counter()
    try:
        schema = getattr(prompts, "SCHEMA", InquiryAnalysis)  # 스키마가 다른 사본은 그때의 스키마를 쓴다
        a = invoke_structured(model, prompts.analyze(messages, logs, tried), schema).model_dump()
    except Exception as e:  # 형식 실패도 결과로 남긴다
        return {"error": f"{type(e).__name__}: {e}"[:300], "seconds": round(time.perf_counter() - start, 1)}
    seconds = round(time.perf_counter() - start, 1)
    reply = a["reply"]
    row = {**a, "seconds": seconds,
           "cause_ok": a["cause"] == case["cause"],
           "checkable_ok": a["system_checkable"] == case["system_checkable"],
           "keyword_ok": any(k in reply or k in a["solution"] for k in case["keywords"])}
    if case.get("forbidden"):
        row["forbidden_hit"] = any(k in reply or k in a["solution"] for k in case["forbidden"])
    if tried:
        row["repeated"] = max(difflib.SequenceMatcher(None, a["solution"], t).ratio() for t in tried) >= 0.8
    return row


def summary(rows: list[dict]) -> dict:
    ok = [r for r in rows if "error" not in r]
    rate = lambda key: round(sum(r[key] for r in ok) / len(rows), 3) if rows else None  # 형식 실패는 틀린 것으로 센다
    retried = [r for r in ok if "repeated" in r]
    guarded = [r for r in ok if "forbidden_hit" in r]
    causes = {}
    for r in rows:
        causes.setdefault(r["id"], set()).add(r.get("cause"))
    return {
        "runs": len(rows), "format_failures": len(rows) - len(ok),
        "cause_accuracy": rate("cause_ok"), "checkable_accuracy": rate("checkable_ok"), "keyword_hit": rate("keyword_ok"),
        "repeated_solution": sum(r["repeated"] for r in retried), "retry_runs": len(retried),
        "forbidden_hit": sum(r["forbidden_hit"] for r in guarded), "forbidden_runs": len(guarded),
        "consistent_cases": round(sum(len(c) == 1 for c in causes.values()) / len(causes), 3) if causes else None,
        "median_seconds": statistics.median(r["seconds"] for r in rows) if rows else None,
    }


def main(experiment: str, repeat: int, only_current: bool = False) -> None:
    model = get_chat_model()
    versions = {current.VERSION: current} if only_current else {FROZEN: frozen(FROZEN), current.VERSION: current}
    report = {"experiment": experiment, "eval_set": EVAL["version"], "repeat": repeat, "versions": {}}
    review = []
    for version, prompts in versions.items():
        rows = []
        for case in EVAL["cases"]:
            for n in range(repeat):
                r = run_case(model, prompts, case)
                rows.append({"id": case["id"], "kind": case["kind"], "run": n + 1, "expect_cause": case["cause"],
                             "expect_checkable": case["system_checkable"], **r})
                print(version, case["id"], n + 1, r.get("cause"), r.get("system_checkable"),
                      "OK" if r.get("cause_ok") and r.get("checkable_ok") else "X", r.get("seconds"), flush=True)
        by_kind = {}
        for cause in ("시스템 측", "지원자 측", "원인 판단 불가"):
            part = [r for r in rows if r["expect_cause"] == cause]
            by_kind[cause] = summary(part)
        report["versions"][version] = {"summary": summary(rows), "by_expected_cause": by_kind, "rows": rows}
        review += [[version, r["id"], r["kind"], r["run"], r["expect_cause"], r.get("cause"), r["expect_checkable"],
                    r.get("system_checkable"), r.get("keyword_ok"), r.get("forbidden_hit"), r.get("problem"),
                    r.get("reply") or r.get("error"), ""]
                   for r in rows]
        print(version, json.dumps(report["versions"][version]["summary"], ensure_ascii=False), flush=True)

    Path("/eval/results").mkdir(exist_ok=True)
    Path(f"/eval/results/inquiry-{experiment}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with Path(f"/eval/results/inquiry-{experiment}-review.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["버전", "ID", "종류", "회차", "정답 원인", "판단 원인", "정답 재검사", "판단 재검사", "안내 적중",
                    "금지어", "문제 원인", "안내(reply)", "사람 판정(적절/부적절)"])
        w.writerows(review)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 2, len(sys.argv) > 3 and sys.argv[3] == "current")
