"""STT 보정 평가 (SYS-004, AI Agent 설계서 T-31). ai-service 이미지에서 실행한다.

stt_eval_set.json의 답변마다 STT 보정을 실제 LLM으로 돌리고 v1 사본(frozen/stt_correction_v1.py)과 지금 버전을 비교한다.
- 고침 적중률: expect_fixes 중 보정문에 right가 있고 wrong이 없는 비율
- 보존율: keep 구간 중 원문 그대로인 비율
- 다시 쓰기: 원문과 보정문의 글자 유사도가 0.6보다 낮은 구간 수 (앱이 막은 뒤의 결과로 센다)
- 형식 실패와 시간
바뀐 구간은 results/stt-<실험 ID>-review.csv에 원문·보정문을 두고 사람이 본다.
LLM이 낸 원래 출력(llm_outputs)도 남긴다. v2에서 LLM이 낸 짝 중 코드가 버린 것을 보기 위해서다 (T2부터).

PC2의 final_project 폴더에서 (PowerShell):
  docker run --rm --env-file pc2/.env -v "${PWD}/ai-service:/src" -v "${PWD}/scripts/rag-eval:/eval" -w /src pc2-ai-service:latest python /eval/run_stt_eval.py <실험 ID> [반복 횟수]
"""

import csv
import importlib.util
import json
import statistics
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

sys.path[:0] = ["/src"]

from app.chains import stt_correction as current
from app.core.llm import get_chat_model
from app.prompts import stt_correction as current_prompts

EVAL = json.loads(Path("/eval/stt_eval_set.json").read_text(encoding="utf-8"))
REWRITE_SIMILARITY = 0.6


def frozen_v1():
    spec = importlib.util.spec_from_file_location("stt_correction_v1", "/eval/frozen/stt_correction_v1.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Recorder:
    """LLM 출력을 그대로 남긴다."""

    def __init__(self, model):
        self.model, self.outputs = model, []

    def invoke(self, messages):
        out = self.model.invoke(messages)
        self.outputs.append(out.content)
        return out


def run_case(model, chain, case: dict) -> dict:
    segments = [{"time_offset_sec": i, "raw_text": s} for i, s in enumerate(case["segments"])]
    model = Recorder(model)
    start = time.perf_counter()
    try:
        out = [s["corrected_text"] for s in chain.correct_transcript(model, case["question"], segments)]
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"[:300], "seconds": round(time.perf_counter() - start, 1),
                "llm_outputs": model.outputs}
    raws = case["segments"]
    hits = [f["right"] in out[f["segment"] - 1] and f["wrong"] not in out[f["segment"] - 1] for f in case["expect_fixes"]]
    kept = [out[i - 1] == raws[i - 1] for i in case["keep"]]
    similarity = [SequenceMatcher(None, r, c).ratio() for r, c in zip(raws, out)]
    return {"corrected": out, "seconds": round(time.perf_counter() - start, 1), "fix_hits": hits, "kept": kept,
            "rewrites": sum(s < REWRITE_SIMILARITY for s in similarity),
            "changed": [i + 1 for i, (r, c) in enumerate(zip(raws, out)) if r != c], "llm_outputs": model.outputs}


def summary(rows: list[dict]) -> dict:
    ok = [r for r in rows if "error" not in r]
    fixes = [h for r in ok for h in r["fix_hits"]]
    kept = [k for r in ok for k in r["kept"]]
    return {"runs": len(rows), "format_failures": len(rows) - len(ok),
            "fix_hit": round(sum(fixes) / len(fixes), 3) if fixes else None, "fix_total": len(fixes),
            "keep_rate": round(sum(kept) / len(kept), 3) if kept else None, "keep_total": len(kept),
            "rewrites": sum(r["rewrites"] for r in ok),
            "median_seconds": statistics.median(r["seconds"] for r in rows) if rows else None}


def main(experiment: str, repeat: int) -> None:
    model = get_chat_model()
    versions = {"v1": frozen_v1(), current_prompts.VERSION: current}
    report = {"experiment": experiment, "eval_set": EVAL["version"], "repeat": repeat, "versions": {}}
    review = []
    for version, chain in versions.items():
        rows = []
        for case in EVAL["cases"]:
            for n in range(repeat):
                r = run_case(model, chain, case)
                rows.append({"id": case["id"], "kind": case["kind"], "run": n + 1, **r})
                print(version, case["id"], n + 1, "고침", sum(r.get("fix_hits", [])), "/", len(case["expect_fixes"]),
                      "보존", sum(r.get("kept", [])), "/", len(case["keep"]), "다시 쓰기", r.get("rewrites"),
                      r.get("error", ""), r["seconds"], flush=True)
                for i in r.get("changed", []):
                    review.append([version, case["id"], n + 1, i, case["segments"][i - 1], r["corrected"][i - 1], ""])
        report["versions"][version] = {"summary": summary(rows), "rows": rows}
        print(version, json.dumps(report["versions"][version]["summary"], ensure_ascii=False), flush=True)

    Path("/eval/results").mkdir(exist_ok=True)
    Path(f"/eval/results/stt-{experiment}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with Path(f"/eval/results/stt-{experiment}-review.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["버전", "ID", "회차", "구간", "원문", "보정문", "사람 판정(바름/틀림/다시 씀)"])
        w.writerows(review)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 2)
