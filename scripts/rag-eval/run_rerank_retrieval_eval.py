"""RAG 개선 2-③ 리랭커 검색 평가. 1단계 평가셋(rag_eval_set.json)으로 벡터 순위와 리랭커 순위를 비교한다.

공고 8452(E4c, 128토큰 + 문맥). 검색어마다 벡터 상위 20개를 후보로 두고(검색기와 같은 128토큰 분할, 조각별 최고 유사도),
리랭커(bge-reranker-v2-m3)로 다시 정렬한다. 개선 2-②에서 고른 기준값(C 0.05, D 0.005)이 다른 데이터에서도 맞는지도 본다.
정답 판정은 run_retrieval_eval.py와 같다 (gold 문장을 담은 청크, 경계에서 잘리면 절반 이상 담은 쪽).

1) candidates: 로컬 python, PC1 postgres·embed-server(localhost)를 쓴다.
     python scripts/rag-eval/run_rerank_retrieval_eval.py candidates
2) score: PC1 embed-server 이미지 (GPU). final_project 폴더에서 (Git Bash면 MSYS_NO_PATHCONV=1을 앞에 붙인다):
     docker run --rm --gpus all -v pc1_embed-models:/models -e HF_HOME=/models/hf -e HF_HUB_OFFLINE=1 -v "$(pwd)/scripts/rag-eval:/eval" pc1-embed-server python /eval/run_rerank_retrieval_eval.py score
3) report: 로컬 python.
     python scripts/rag-eval/run_rerank_retrieval_eval.py report
"""

import json
import math
import random
import re
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
RESULTS = HERE / "results"
CANDIDATES = RESULTS / "rerank-retrieval-candidates-E4c.json"
SCORES = RESULTS / "rerank-retrieval-E4c-bge-m3.json"
POSTING, MAX_TOKENS, TOP = 8452, 128, 20
MODEL = "BAAI/bge-reranker-v2-m3"
EMPTY_EXPECTED = {"관계없음", "㉠"}  # run_retrieval_eval.py와 같다
TOP_K, MIN_SIMILARITY = 5, 0.50


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _has_gold(chunk: str, gold: list[str]) -> bool:
    """run_retrieval_eval.py와 같다."""
    for g in gold:
        half = (len(g) + 1) // 2
        if g in chunk or any(chunk.endswith(g[:n]) or chunk.startswith(g[-n:]) for n in range(half, len(g))):
            return True
    return False


def candidates():
    import httpx
    import psycopg

    root = HERE.parent.parent
    sys.path.insert(0, str(root / "ai-service"))
    from app.rag.chunking import split_by_offsets

    env = dict(l.split("=", 1) for l in (root / "pc1/.env").read_text(encoding="utf-8").splitlines()
               if "=" in l and not l.startswith("#"))
    http = httpx.Client(base_url="http://localhost:8001", headers={"X-Internal-Token": env["INTERNAL_TOKEN"].strip()},
                        timeout=60)
    db = psycopg.connect(host="localhost", port=5432, user=env["POSTGRES_USER"].strip(),
                         password=env["POSTGRES_PASSWORD"].strip(), dbname=env["POSTGRES_DB"].strip())
    out = []
    for q in json.loads((HERE / "rag_eval_set.json").read_text(encoding="utf-8"))["queries"]:
        offsets = [tuple(o) for o in http.post("/tokenize", json={"texts": [q["query"]]}).json()["offsets"][0]]
        pieces = split_by_offsets(q["query"], offsets, MAX_TOKENS, overlap=0)
        best = {}
        for v in http.post("/embed", json={"texts": pieces}).json()["vectors"]:
            for cid, sim, content in db.execute(
                    "select chunk_id, 1 - (embedding <=> %s::vector), content from doc_chunk where posting_id = %s "
                    "order by embedding <=> %s::vector limit %s", (str(v), POSTING, str(v), TOP)):
                if cid not in best or sim > best[cid][0]:
                    best[cid] = (sim, content)
        gold = [_norm(g) for g in q["gold"]]
        top = sorted(best.items(), key=lambda x: -x[1][0])[:TOP]
        out.append({"id": q["id"], "kind": q["kind"], "expect": q["expect"], "has_gold": bool(gold), "query": q["query"],
                    "pieces": pieces,
                    "candidates": [{"chunk_id": c, "similarity": round(s, 4), "gold": bool(gold) and _has_gold(_norm(t), gold),
                                    "content": t} for c, (s, t) in top]})
    CANDIDATES.write_text(json.dumps({"posting_id": POSTING, "query_max_tokens": MAX_TOKENS, "top": TOP, "queries": out},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(out), "검색어 저장:", CANDIDATES)


def score():
    from sentence_transformers import CrossEncoder

    model = CrossEncoder(MODEL, max_length=1024, device="cuda")
    out = []
    for q in json.loads(CANDIDATES.read_text(encoding="utf-8"))["queries"]:
        start = time.perf_counter()
        texts = q["pieces"]
        flat = [float(s) for s in model.predict([(t, c["content"]) for c in q["candidates"] for t in texts])]
        probs = [max(flat[i * len(texts):(i + 1) * len(texts)]) for i in range(len(q["candidates"]))]
        out.append({"id": q["id"], "seconds": round(time.perf_counter() - start, 3),
                    "scores": {c["chunk_id"]: round(p, 4) for c, p in zip(q["candidates"], probs)}})
        print(q["id"], f"{out[-1]['seconds']}s")
    SCORES.write_text(json.dumps({"model": MODEL, "mode": "pieces", "results": out}, ensure_ascii=False, indent=1),
                      encoding="utf-8")


def _rank(cands: list[dict]) -> int | None:
    return next((i + 1 for i, c in enumerate(cands) if c["gold"]), None)


def _boot(diffs, n=20000):
    rnd = random.Random(0)
    s = sorted(statistics.mean(rnd.choices(diffs, k=len(diffs))) for _ in range(n))
    return s[int(.025 * n)], s[int(.975 * n)]


def _mcnemar(b, c):  # 정확 이항 검정, 양측
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def report():
    queries = json.loads(CANDIDATES.read_text(encoding="utf-8"))["queries"]
    scores = {r["id"]: r for r in json.loads(SCORES.read_text(encoding="utf-8"))["results"]}
    for q in queries:
        for c in q["candidates"]:
            c["rerank"] = scores[q["id"]]["scores"][str(c["chunk_id"])]
    gold_q = [q for q in queries if q["has_gold"]]
    empty_q = [q for q in queries if q["expect"] in EMPTY_EXPECTED]
    outside = [q["id"] for q in gold_q if _rank(q["candidates"]) is None]
    print(f"검색어 {len(queries)}개: 정답 있음 {len(gold_q)}, 비어야 함 {len(empty_q)}. 정답이 벡터 상위 {TOP} 밖: {outside}")

    vec = {q["id"]: _rank(q["candidates"]) for q in gold_q}
    rr = {q["id"]: _rank(sorted(q["candidates"], key=lambda c: -c["rerank"])) for q in gold_q}
    big = 10 ** 9
    print(f"\n{'':<10} {'R@1':>6} {'R@3':>6} {'R@5':>6} {'R@10':>6} {'MRR':>6}")
    for name, ranks in (("벡터", vec), ("리랭커", rr)):
        r = [ranks[q["id"]] or big for q in gold_q]
        print(f"{name:<10} " + " ".join(f"{sum(x <= k for x in r) / len(r):6.1%}" for k in (1, 3, 5, 10))
              + f" {statistics.mean(1 / x if x < big else 0 for x in r):6.3f}")
    for k in (1, 5):
        up = [i for i in vec if (rr[i] or big) <= k < (vec[i] or big)]
        down = [i for i in vec if (vec[i] or big) <= k < (rr[i] or big)]
        print(f"R@{k}: 리랭커로 새로 찾음 {up}, 잃음 {down}, McNemar p={_mcnemar(len(up), len(down)):.3f}")
    d = [(1 / rr[i] if rr[i] else 0) - (1 / vec[i] if vec[i] else 0) for i in vec]
    lo, hi = _boot(d)
    print(f"MRR 차이 {statistics.mean(d):+.3f}, 95% CI [{lo:+.3f}, {hi:+.3f}]")

    print(f"\n생성에 넘길 청크(상위 {TOP_K}) 기준: 정답 있는 검색어 중 정답이 남은 비율 / 비어야 할 검색어 중 실제로 빈 비율 / 정답 있는데 다 버림")

    def kept_a(q):
        return [c for c in q["candidates"] if c["similarity"] >= MIN_SIMILARITY][:TOP_K]

    def show(name, keep):
        hit = sum(any(c["gold"] for c in keep(q)) for q in gold_q) / len(gold_q)
        empty = sum(not keep(q) for q in empty_q) / len(empty_q)
        lost = [q["id"] for q in gold_q if not keep(q)]
        print(f"  {name:<28} {hit:6.1%} / {empty:6.1%} / {lost}")

    show("A 지금(유사도≥0.50)", kept_a)
    for t in (0.005, 0.01, 0.02):
        show(f"D A + 리랭커<{t} 버림", lambda q, t=t: [c for c in kept_a(q) if c["rerank"] >= t])
    for t in (0.01, 0.02, 0.05, 0.1):
        show(f"C 리랭커≥{t}(상위{TOP}에서)",
             lambda q, t=t: [c for c in sorted(q["candidates"], key=lambda c: -c["rerank"]) if c["rerank"] >= t][:TOP_K])
    secs = [r["seconds"] for r in scores.values()]
    print(f"\n리랭커 시간(후보 {TOP}개): 중앙 {statistics.median(secs):.2f}초, 최대 {max(secs):.2f}초")


if __name__ == "__main__":
    {"candidates": candidates, "score": score, "report": report}[sys.argv[1]]()
