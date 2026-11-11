"""서류 보고서 항목 점수 평가 (RAG 설계서 5.3의 채점 지표). ai-service 이미지에서 실행한다.

document_eval_set.json의 지원자마다 score_document_items로 채점하고, document_human_scores.csv의
기준 점수와 비교한다. 기준 점수 칸이 빈 축은 오차를 재지 않는다.
- 항목 점수 오차: LLM 항목 점수와 기준 항목 점수(축 점수 × 비율)의 평균 절대 차이
- 축별 점수 오차: 축마다 평균 절대 차이와 평균 차이(+면 LLM이 후하다)
- 순서: 항목마다 지원자 3명의 점수 순서가 기준과 같은지

인재상 적합도, 강점·확인 필요, 요약은 글이라 오차를 재지 않는다. 코드 확인(점수 숫자·이름이 들어갔는지,
요약 문장 수)을 요약에 넣고, 사람이 문장마다 판정할 표 results/document-<실험 ID>-review.csv를 만든다.

필요한 것: postgres, embed-server, LLM 서버. 먼저 index_eval_posting.py로 공고를 색인한다.

PC2의 final_project 폴더에서 (PowerShell, pc2/.env에 DB·embed-server·LLM 주소가 있다):
  docker run --rm --env-file pc2/.env -v "${PWD}/ai-service:/src" -v "${PWD}/scripts/rag-eval:/eval" -w /src pc2-ai-service:latest python /eval/run_document_eval.py <공고 ID> <실험 ID>
"""

import csv
import json
import re
import statistics
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.path[:0] = ["/src"]

from app.chains.document_report import NO_FIT_NOTE, build_document_report
from app.core.config import get_settings
from app.core.llm import get_chat_model
from app.prompts import document_report as prompts
from app.rag.evidence import split_sentences
from app.rag.retriever import search_company_docs
from app.schemas.internal import ApplicantDocuments, PostingBrief

EVAL = json.loads(Path("/eval/document_eval_set.json").read_text(encoding="utf-8"))
SCORES = Path("/eval/document_human_scores.csv")


def reference_axes() -> dict[tuple[str, str], dict[str, float]]:
    """(지원자, 항목) → {축 key: 기준 점수}. 빈 칸은 넣지 않는다."""
    keys = {(item, ax["name"]): ax["key"] for item, axes in EVAL["axes"].items() for ax in axes}
    out: dict[tuple[str, str], dict[str, float]] = {}
    with SCORES.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            value = row["[채점] 점수 0~100"].strip()
            if value:
                out.setdefault((row["지원자"], row["항목"]), {})[keys[(row["항목"], row["축"])]] = float(value)
    return out


def reference_item(item: str, axes: dict[str, float]) -> float | None:
    """모든 축에 기준 점수가 있을 때만 항목 점수를 계산한다."""
    ratios = {ax["key"]: ax["ratio"] for ax in EVAL["axes"][item]}
    if set(ratios) - set(axes):
        return None
    return sum(axes[k] * r for k, r in ratios.items()) / 100


def evaluate(posting_id: int) -> tuple[list[dict], list[dict]]:
    posting = PostingBrief(posting_id=posting_id, **EVAL["posting"])
    refs = reference_axes()
    rows, reports = [], []
    for a in EVAL["applicants"]:
        started = time.perf_counter()
        report = build_document_report(
            posting, ApplicantDocuments(**a["documents"]), model=get_chat_model(),
            search=lambda texts: search_company_docs(posting_id, texts),
        )
        seconds = round(time.perf_counter() - started, 1)
        reports.append({
            "applicant": a["id"],
            "name": a["documents"]["personal"].get("name", ""),
            "fits": [{"talent_content": f.talent_content, "evidence": f.evidence} for f in report.fits],
            "points": [{"point_type": p.point_type, "item": p.item, "content": p.content} for p in report.points],
            "summary": report.summary,
            "llm_output": report.llm_output,
            "seconds": seconds,
        })
        print(f"{a['id']} 요약: {report.summary}", flush=True)
        for item in report.items:
            ref_axes = refs.get((a["id"], item.name), {})
            ref_score = reference_item(item.name, ref_axes)
            rows.append({
                "applicant": a["id"],
                "item": item.name,
                "score": float(item.score),
                "reference_score": round(ref_score, 2) if ref_score is not None else None,
                "axes": {k: float(v) for k, v in item.axes.items()},
                "reference_axes": ref_axes,
                "reason": item.reason,
                "evidence": [f"[{e.id}] {e.text}" for e in item.evidence],
                "llm_output": item.llm_output,
                "applicant_seconds": seconds,
            })
            print(f"{a['id']} {item.name}: {item.score} (기준 {ref_score}) 축 {rows[-1]['axes']}", flush=True)
    return rows, reports


_SCORE_NUMBER = re.compile(r"\d+(\.\d+)?\s*점")


def check_texts(reports: list[dict]) -> dict:
    """글 결과의 코드 확인. 점수 숫자와 이름은 쓰지 말라고 했다 (프롬프트 v3)."""
    texts = [(r, p["content"]) for r in reports for p in r["points"]] + [(r, r["summary"]) for r in reports]
    return {
        "points": sum(len(r["points"]) for r in reports),
        "fits_found": sum(f["evidence"] != NO_FIT_NOTE for r in reports for f in r["fits"]),
        "fits_total": sum(len(r["fits"]) for r in reports),
        "with_score_number": [t for _, t in texts if _SCORE_NUMBER.search(t)],
        "with_name": [t for r, t in texts if r["name"] and r["name"] in t],
        "summary_sentences": {r["applicant"]: len(split_sentences(r["summary"])) for r in reports},
    }


def write_review(reports: list[dict], path: Path) -> None:
    """사람이 문장마다 판정할 표. 인재상 적합도는 '근거가 그 인재상과 맞나(또는 확인 안 됨이 맞나)'를 본다."""
    header = ["지원자", "구분", "관련 항목", "내용", "참고: 근거 (서류에서 읽은 일)", "[판정] 맞음/틀림/애매", "[판정] 메모"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in reports:
            for fit in r["fits"]:
                w.writerow([r["applicant"], "인재상 적합도", "", fit["talent_content"], fit["evidence"], "", ""])
            for p in r["points"]:
                w.writerow([r["applicant"], p["point_type"], p["item"], p["content"], "", "", ""])
            for sentence in split_sentences(r["summary"]):
                w.writerow([r["applicant"], "요약", "", sentence, "", "", ""])


def summarize(rows: list[dict]) -> dict:
    scored = [r for r in rows if r["reference_score"] is not None]
    axis_diffs: dict[str, list[float]] = {}
    for r in rows:
        for k, ref in r["reference_axes"].items():
            if k in r["axes"] and k != "skill":  # 필수 기술은 코드 계산이라 오차가 없다
                axis_diffs.setdefault(f"{r['item']}/{k}", []).append(r["axes"][k] - ref)
    order = {}
    for item in EVAL["axes"]:
        rs = [r for r in scored if r["item"] == item]
        if len(rs) == len(EVAL["applicants"]):
            llm = [r["applicant"] for r in sorted(rs, key=lambda r: -r["score"])]
            ref = [r["applicant"] for r in sorted(rs, key=lambda r: -r["reference_score"])]
            order[item] = {"llm": llm, "reference": ref, "same": llm == ref}
    return {
        "item_score_error": round(statistics.mean(abs(r["score"] - r["reference_score"]) for r in scored), 2) if scored else None,
        "items_with_reference": len(scored),
        "axis_error": {k: {"mae": round(statistics.mean(abs(d) for d in v), 1), "bias": round(statistics.mean(v), 1)}
                       for k, v in axis_diffs.items()},
        "order": order,
    }


def main() -> None:
    posting_id, experiment = int(sys.argv[1]), sys.argv[2]
    settings = get_settings()
    rows, reports = evaluate(posting_id)
    summary = summarize(rows) | {"texts": check_texts(reports)}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    out = Path(f"/eval/results/document-{experiment}.json")
    out.write_text(json.dumps({
        "experiment": experiment,
        "eval_set": EVAL["version"],
        "prompt": prompts.VERSION,
        "model": settings.LLM_MODEL,
        "summary": summary,
        "rows": rows,
        "reports": reports,
    }, ensure_ascii=False, indent=2, default=lambda o: float(o) if isinstance(o, Decimal) else str(o)), encoding="utf-8")
    review = Path(f"/eval/results/document-{experiment}-review.csv")
    write_review(reports, review)
    print(out, review)


if __name__ == "__main__":
    main()
