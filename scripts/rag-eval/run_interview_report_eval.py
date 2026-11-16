"""면접 보고서 평가 (루브릭 설계서 8·10.2). ai-service 이미지에서 실행한다.

interview_report_eval_set.json의 가상 지원자마다 build_interview_report를 실제 LLM으로 돌리고 아래를 남긴다.
- 인재상 적합도: 정답(expected_fits)과 비교한 답변 단위 정밀도·재현율, LLM이 낸 없는 번호 수
- 요약: 숫자가 들어갔는지(점수를 옮겨 씀), 문장 수
- 항목 점수·강점·확인 필요(코드)와 시간
요약과 인재상 근거의 품질은 사람이 본다. results/interview-report-<실험 ID>-review.csv에 판정 칸을 둔다.
LLM 판정을 다시 돌려도 같은지 보려고 반복 횟수를 받는다.

PC2의 final_project 폴더에서 (PowerShell):
  docker run --rm --env-file pc2/.env -v "${PWD}/ai-service:/src" -v "${PWD}/scripts/rag-eval:/eval" -w /src pc2-ai-service:latest python /eval/run_interview_report_eval.py <실험 ID> [반복 횟수] [버전들]
세트 v2부터 분야가 다른 공고(R4·R5)의 근거 수(mismatched_fits, 0이어야 함)를 따로 센다.
"""

import csv
import importlib.util
import json
import re
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.path[:0] = ["/src"]

from app.chains import interview_report as chain
from app.core.llm import get_chat_model
from app.prompts import interview_report as prompts
from app.schemas.internal import AnswerRecord, PostingBrief

EVAL = json.loads(Path("/eval/interview_report_eval_set.json").read_text(encoding="utf-8"))
RAG = {q["id"]: q for q in json.loads(Path("/eval/rag_eval_set.json").read_text(encoding="utf-8"))["queries"]}
SCORED = {r["id"]: r for r in json.loads(Path("/eval/results/content-P16-v4.json").read_text(encoding="utf-8"))["rows"]}
POSTING = PostingBrief(posting_id=0, **json.loads(Path("/eval/document_eval_set.json").read_text(encoding="utf-8"))["posting"])
_DIGIT = re.compile(r"\d")


def records(applicant: dict) -> tuple[list[AnswerRecord], list[str]]:
    out, ids = [], []
    for a in applicant["answers"]:
        q, scored = RAG[a["answer"]], SCORED[a["answer"]]
        out.append(AnswerRecord(
            question_text=RAG[q["question"]]["query"], kind="AI", corrected_text=q["query"],
            content_score=Decimal(scored["score"]), content_reason=scored["reason"],
            speech_score=Decimal(a["speech"]), expression_score=None if a["face"] is None else Decimal(a["face"]),
            main_expression=a["main"], silence_sec=Decimal(a["silence"]), filler_count=a["fillers"],
            response_delay_sec=Decimal(a["delay"]),
        ))
        ids.append(a["answer"])
    return out, ids


def fit_pairs(fits, talents, ids) -> set[tuple[str, str]]:
    """(인재상 번호, 답변 ID) 짝. 근거의 'Qn 답변'을 답변 ID로 바꾼다."""
    by_text = {text: tid for tid, text in talents}
    pairs = set()
    for f in fits:
        for n in re.findall(r"Q(\d+) 답변", f.evidence):
            pairs.add((by_text[f.talent_content], ids[int(n) - 1]))
    return pairs


def posting_of(applicant: dict) -> PostingBrief:
    """지원자의 공고. 없으면 document_eval_set.json의 공고 (세트 v2: 분야가 다른 공고 spring)."""
    key = applicant.get("posting")
    return PostingBrief(posting_id=0, **EVAL["postings"][key]) if key else POSTING


def frozen(version: str):
    spec = importlib.util.spec_from_file_location(f"interview_report_{version}", f"/eval/frozen/interview_report_{version}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_version(model, prompts_module, repeat: int) -> tuple[dict, list[dict], list[list]]:
    chain.prompts = prompts_module  # 체인이 쓰는 프롬프트 모듈을 바꿔 끼운다 (평가 전용)
    rows, review = [], []
    for applicant in EVAL["applicants"]:
        answers, ids = records(applicant)
        posting = posting_of(applicant)
        talents = chain._talents(posting)
        expected = {(t, a) for t, answer_ids in applicant["expected_fits"].items() for a in answer_ids}
        for n in range(repeat):
            start = time.perf_counter()
            report = chain.build_interview_report(posting, answers, model=model)
            seconds = round(time.perf_counter() - start, 1)
            got = fit_pairs(report.fits, talents, ids)
            picked = [sid for f in (report.llm_outputs["talent_fit"] or {}).get("fits", []) for sid in f["sentence_ids"]]
            valid = set(chain._answer_sentences(answers))
            row = {
                "applicant": applicant["id"], "run": n + 1, "seconds": seconds, "mismatched": bool(applicant.get("posting")),
                "items": {i.name: str(i.score) for i in report.items},
                "fit_found": len(got), "fit_correct": len(got & expected), "fit_expected": len(expected),
                "fit_invalid_ids": sum(sid not in valid for sid in picked),
                "summary_has_digit": bool(_DIGIT.search(report.summary)),
                "summary": report.summary,
                "fits": [{"talent": f.talent_content, "evidence": f.evidence} for f in report.fits],
                "points": [{"type": p.point_type, "item": p.item, "content": p.content} for p in report.points],
                "llm": report.llm_outputs,
            }
            rows.append(row)
            print(prompts_module.VERSION, applicant["id"], n + 1, f"fit {row['fit_correct']}/{row['fit_found']} (정답 {len(expected)})",
                  f"없는 번호 {row['fit_invalid_ids']}", f"요약 숫자 {row['summary_has_digit']}", f"{seconds}초", flush=True)
            for f in report.fits:
                review.append([prompts_module.VERSION, applicant["id"], n + 1, "인재상", f.talent_content, f.evidence, ""])
            review.append([prompts_module.VERSION, applicant["id"], n + 1, "요약", "", report.summary, ""])

    same = [r for r in rows if not r["mismatched"]]
    found = sum(r["fit_found"] for r in same)
    correct = sum(r["fit_correct"] for r in same)
    expected = sum(r["fit_expected"] for r in same)
    summary = {
        "runs": len(rows),
        # 같은 분야 공고(R1~R3)의 정밀도·재현율
        "fit_precision": round(correct / found, 3) if found else None,
        "fit_recall": round(correct / expected, 3) if expected else None,
        # 분야가 다른 공고(R4·R5)에서 고른 근거 수. 0이어야 한다
        "mismatched_fits": sum(r["fit_found"] for r in rows if r["mismatched"]),
        "fit_invalid_ids": sum(r["fit_invalid_ids"] for r in rows),
        "summary_with_digit": sum(r["summary_has_digit"] for r in rows),
        "median_seconds": sorted(r["seconds"] for r in rows)[len(rows) // 2],
    }
    print(prompts_module.VERSION, json.dumps(summary, ensure_ascii=False), flush=True)
    return summary, rows, review


def main(experiment: str, repeat: int, versions: list[str]) -> None:
    model = get_chat_model()
    report = {"experiment": experiment, "eval_set": EVAL["version"], "versions": {}}
    review = []
    for version in versions:
        module = prompts if version == prompts.VERSION else frozen(version)
        summary, rows, lines = run_version(model, module, repeat)
        report["versions"][version] = {"summary": summary, "rows": rows}
        review += lines
    Path("/eval/results").mkdir(exist_ok=True)
    Path(f"/eval/results/interview-report-{experiment}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with Path(f"/eval/results/interview-report-{experiment}-review.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["버전", "지원자", "회차", "종류", "인재상·항목", "내용", "사람 판정(맞음/틀림)"])
        w.writerows(review)


if __name__ == "__main__":
    # 사용법: <실험 ID> [반복 횟수] [버전들, 쉼표로. 기본은 지금 버전만]. 고정 사본은 frozen/interview_report_<버전>.py
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 2,
         sys.argv[3].split(",") if len(sys.argv) > 3 else [prompts.VERSION])
