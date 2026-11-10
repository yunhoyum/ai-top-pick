"""human_scores.csv(기준 점수)를 rag_eval_set.json에 넣는다. CSV를 고치면 다시 실행한다.

- CSV에 있고 평가셋에 없는 면접 답변을 더한다
- 답변마다 기준 점수(reference)를 넣고, 기대 근거 상태(expect)를 기준 점수에서 정한다
- 판단에 쓴 문서 문장을 정답 문장(gold)에 더한다. 문서에 없는 문장이면 멈춘다

ai-service 이미지에서 실행한다 (PDF 텍스트를 main-api 추출기 대신 저장된 청크로 확인한다).
final_project 폴더에서:
  docker run --rm --network pc1_default --env-file pc1/.env \
    -v "$(pwd)/ai-service:/src" -v "$(pwd)/scripts/rag-eval:/eval" -w /src pc2-ai-service:latest \
    python /eval/apply_human_scores.py <평가 공고 ID>
"""

import csv
import io
import json
import re
import sys
from pathlib import Path

sys.path[:0] = ["/src"]

from sqlalchemy import text

from app.db.session import get_engine

EVAL = Path("/eval/rag_eval_set.json")
SCORES = Path("/eval/human_scores.csv")
LEVELS = {"같음", "대부분 같음", "일부만 같음", "반대", "문서에 없음"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _expect(ref: dict) -> str:
    """기준 점수에서 기대 근거 상태를 정한다 (루브릭 설계서 3.3 판정 순서)."""
    if ref["relevance"] == 0 and ref["specificity"] == 0:
        return "무응답"
    if not ref["question_in_docs"]:
        return "㉠"
    if ref["level"] == "문서에 없음":
        return "㉡"
    return "근거 있음"


def main(posting_id: int) -> None:
    data = json.loads(EVAL.read_text(encoding="utf-8"))
    by_id = {q["id"]: q for q in data["queries"]}
    with get_engine().connect() as c:
        doc = _norm("".join(c.scalars(text("SELECT content FROM doc_chunk WHERE posting_id = :p"), {"p": posting_id})))

    rows = list(csv.DictReader(io.StringIO(SCORES.read_bytes().decode("utf-8-sig"))))
    missing = []
    for row in rows:
        aid = row["답변 ID"]
        evidence = [s.strip() for s in row["[채점] 판단에 쓴 문서 문장 (선택)"].splitlines() if s.strip()]
        missing += [(aid, s) for s in evidence if _norm(s.lstrip("•").strip()) not in doc]
        level = row["[채점] 일치 단계 (같음/대부분 같음/일부만 같음/반대/문서에 없음)"].strip() or None
        if level and level not in LEVELS:
            raise SystemExit(f"{aid}: 일치 단계 '{level}'를 알 수 없습니다.")
        ref = {
            "relevance": int(row["[채점] 질문 적합성 0~100"]),
            "specificity": int(row["[채점] 구체성 0~100"]),
            "question_in_docs": row["[채점] 질문 주제가 문서에 있나 (예/아니오)"].strip() == "예",
            "level": level,
            "evidence": evidence,
            # 메모가 '[사람 확인]'으로 시작하는 줄만 사람이 직접 정했다. 나머지는 AI가 매긴 초안이다
            "human_reviewed": row["[채점] 메모"].startswith("[사람 확인]"),
            "memo": row["[채점] 메모"],
        }
        entry = by_id.get(aid)
        if entry is None:
            entry = {"id": aid, "kind": "면접 답변", "question": row["질문 ID"], "query": row["지원자 답변"], "gold": []}
            data["queries"].append(entry)
            by_id[aid] = entry
        entry["reference"] = ref
        entry["expect"] = _expect(ref)
        entry["gold"] += [s.lstrip("•").strip() for s in evidence if s.lstrip("•").strip() not in entry["gold"]]

    if missing:
        raise SystemExit("문서에서 찾지 못한 근거 문장:\n" + "\n".join(f"  {a}: {s}" for a, s in missing))

    data["version"] = "v3"
    data["description"] = re.sub(r"평가셋 v[\d.]+", "평가셋 v3", data["description"])
    data["changes"] += (
        " v2.1 → v3 (2026-11-10): 면접 답변을 30개로 늘리고(A10~A30) 답변마다 기준 점수(reference)를 넣었다. "
        "기대 근거 상태(expect)는 기준 점수에서 정한다. 기준 점수는 AI가 매긴 초안에 사람이 A5·A10·A19·A27을 확인해 고쳤다 "
        "(human_reviewed). 판단에 쓴 문서 문장을 정답 문장에 더했다."
    )
    EVAL.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    answers = [q for q in data["queries"] if q["kind"] == "면접 답변"]
    counts = {}
    for q in answers:
        counts[q["expect"]] = counts.get(q["expect"], 0) + 1
    print(f"면접 답변 {len(answers)}개, 사람 확인 {sum(q['reference']['human_reviewed'] for q in answers)}개, 기대 상태 {counts}")


if __name__ == "__main__":
    main(int(sys.argv[1]))
