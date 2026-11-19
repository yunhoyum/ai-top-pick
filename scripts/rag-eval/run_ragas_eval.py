"""질문 생성 RAGAS 평가 (2단계). 정답 라벨 없이 판정 LLM으로 두 지표를 잰다.

- ContextRelevance: 서류 문장(검색어)으로 찾은 청크가 그 문장과 관련 있는가
- ResponseGroundedness: 생성된 질문이 검색된 청크에 근거하는가
두 지표 모두 판정 LLM이 0·1·2를 매기고 0~1로 바꾼다. 검색 결과를 쓴 직무 질문(경로 '통과')만 본다.
fallback·template 질문은 검색 결과를 쓰지 않아 빼고, 개수만 센다.

판정 모델은 Claude다. 평가용 서류와 가상 공고만 보낸다 (사용자 결정 2026-11-19).
Anthropic SDK가 temperature를 받지 않아 판정이 실행마다 흔들릴 수 있다. 그래서 같은 입력을 REPEAT번 판정한다.

ai-service 이미지가 아니라 별도 venv에서 돌린다:
  python -m venv ragas-venv && ragas-venv/Scripts/pip install ragas langchain-anthropic anthropic "instructor>=1.17"
  ANTHROPIC_API_KEY가 있어야 한다.

  1) 점수: python scripts/rag-eval/run_ragas_eval.py score <라벨> <question-*.json> [...]
     같은 설정으로 여러 번 돌린 질문 생성 결과를 합친다.
     results/ragas-<라벨>.json과 사람 판정용 results/ragas-<라벨>-review.csv를 만든다. CSV에는 RAGAS 점수를 넣지 않는다.
  2) 일치도: CSV의 [사람] 칸을 0·1·2로 채운 뒤 python scripts/rag-eval/run_ragas_eval.py agree <라벨>
"""

import asyncio
import csv
import json
import random
import statistics
import sys
from pathlib import Path

RESULTS = Path(__file__).parent / "results"
JUDGE_MODEL = "claude-sonnet-5-5"
REPEAT = 2
METRICS = ("context_relevance", "response_groundedness")
HUMAN = {"context_relevance": "[사람] 청크 관련도 (0·1·2)", "response_groundedness": "[사람] 질문 근거 (0·1·2)"}


def samples(paths: list[str]) -> tuple[list[dict], dict]:
    rows, skipped = [], {"fallback": 0, "template": 0, "청크 없음": 0}
    for p in paths:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        for r in data["results"]:
            for i, q in enumerate(r["questions"], start=1):
                if q["type"] != "직무":
                    continue
                if q.get("path") != "통과":
                    skipped[q.get("path")] = skipped.get(q.get("path"), 0) + 1
                    continue
                if not q.get("chunks"):
                    skipped["청크 없음"] += 1
                    continue
                rows.append({"key": f"{data['experiment']}/{r['applicant']}/{i}", "user_input": q["query"],
                             "retrieved_contexts": q["chunks"], "response": q["question"]})
    return rows, skipped


async def judge(rows: list[dict]) -> None:
    from anthropic import AsyncAnthropic
    from ragas.llms import llm_factory
    from ragas.metrics.collections import ContextRelevance, ResponseGroundedness

    llm = llm_factory(JUDGE_MODEL, provider="anthropic", client=AsyncAnthropic(), max_tokens=1024)
    relevance, grounded = ContextRelevance(llm=llm), ResponseGroundedness(llm=llm)
    sem = asyncio.Semaphore(4)

    async def one(row: dict) -> None:
        async with sem:
            row["context_relevance"] = [
                (await relevance.ascore(user_input=row["user_input"], retrieved_contexts=row["retrieved_contexts"])).value
                for _ in range(REPEAT)]
            row["response_groundedness"] = [
                (await grounded.ascore(response=row["response"], retrieved_contexts=row["retrieved_contexts"])).value
                for _ in range(REPEAT)]
            print(row["key"], row["context_relevance"], row["response_groundedness"], flush=True)

    await asyncio.gather(*(one(r) for r in rows))


def ci(values: list[float], n: int = 20000) -> tuple[float, float]:
    random.seed(0)
    means = sorted(statistics.mean(random.choices(values, k=len(values))) for _ in range(n))
    return round(means[int(0.025 * n)], 3), round(means[int(0.975 * n)], 3)


def score(label: str, paths: list[str]) -> None:
    rows, skipped = samples(paths)
    asyncio.run(judge(rows))
    summary = {"질문 수": len(rows), "뺀 질문": skipped, "판정 모델": JUDGE_MODEL, "반복": REPEAT}
    for m in METRICS:
        means = [statistics.mean(r[m]) for r in rows]
        # 같은 입력을 다시 판정했을 때 바뀐 비율. 판정 흔들림의 크기다
        unstable = sum(len(set(r[m])) > 1 for r in rows) / len(rows)
        summary[m] = {"평균": round(statistics.mean(means), 3), "95% CI": ci(means), "판정이 바뀐 비율": round(unstable, 3)}
    print(json.dumps(summary, ensure_ascii=False, indent=1))

    (RESULTS / f"ragas-{label}.json").write_text(
        json.dumps({"label": label, "sources": [Path(p).name for p in paths], "summary": summary, "rows": rows},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    review = RESULTS / f"ragas-{label}-review.csv"
    with review.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["key", "서류 문장(검색어)", "검색된 청크", "생성된 질문", HUMAN["context_relevance"],
                    HUMAN["response_groundedness"], "[메모]"])
        for r in rows:
            chunks = "\n\n".join(f"[{i}] {c}" for i, c in enumerate(r["retrieved_contexts"], start=1))
            w.writerow([r["key"], r["user_input"], chunks, r["response"], "", "", ""])
    print(f"저장: ragas-{label}.json, {review.name}")


def agree(label: str) -> None:
    rows = {r["key"]: r for r in json.loads((RESULTS / f"ragas-{label}.json").read_text(encoding="utf-8"))["rows"]}
    with (RESULTS / f"ragas-{label}-review.csv").open(encoding="utf-8-sig") as f:
        human = list(csv.DictReader(f))
    for m in METRICS:
        pairs = [(int(h[HUMAN[m]]) / 2, statistics.mean(rows[h["key"]][m])) for h in human if h[HUMAN[m]].strip()]
        if not pairs:
            print(f"{m}: 사람 판정 없음")
            continue
        exact = sum(abs(a - b) < 0.25 for a, b in pairs) / len(pairs)
        diff = statistics.mean(b - a for a, b in pairs)
        corr = statistics.correlation(*zip(*pairs)) if len({a for a, _ in pairs}) > 1 and len({b for _, b in pairs}) > 1 else None
        print(f"{m}: {len(pairs)}개, 같은 단계 {exact:.0%}, RAGAS − 사람 평균 {diff:+.3f}, 상관 {corr if corr is None else round(corr, 3)}")


if __name__ == "__main__":
    cmd, label, *paths = sys.argv[1:]
    score(label, paths) if cmd == "score" else agree(label)
