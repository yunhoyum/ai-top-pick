"""RAG 개선 2-② 리랭커 점수와, 지금 방식·LLM 필터·리랭커 비교.

score: results/rerank-candidates-E4c.json의 후보(검색어마다 벡터 상위 8개)를 리랭커로 점수 매긴다.
  PC1 embed-server 이미지에서 실행한다 (sentence-transformers, GPU). 모델은 embed-models 볼륨에 받아 두었다.
  final_project 폴더에서:
    docker run --rm --gpus all -v pc1_embed-models:/models -e HF_HOME=/models/hf -e HF_HUB_OFFLINE=1 -v "$(pwd)/scripts/rag-eval:/eval" pc1-embed-server python /eval/run_rerank_eval.py score
compare: 사람 관련도(results/rerank-E4c-review.csv)를 정답으로 세 방식을 비교한다. 로컬 python으로 돌린다.
    python scripts/rag-eval/run_rerank_eval.py compare [필터 실험 ID]
"""

import csv
import json
import sys
import time
from pathlib import Path

RESULTS = Path(__file__).parent / "results"
MODEL = "BAAI/bge-reranker-v2-m3"
TOP_K, MIN_SIMILARITY = 5, 0.50  # 지금 설정 (app/core/config.py)
RERANK_THRESHOLDS = (0.01, 0.02, 0.05, 0.1, 0.2, 0.3)


def load_candidates():
    return json.loads((RESULTS / "rerank-candidates-E4c.json").read_text(encoding="utf-8"))["queries"]


def score():
    from sentence_transformers import CrossEncoder

    model = CrossEncoder(MODEL, max_length=1024, device="cuda")
    out = []
    for q in load_candidates():
        start = time.perf_counter()
        # 레이블이 하나인 CrossEncoder는 기본으로 시그모이드를 씌워 0~1을 돌려준다
        probs = [float(s) for s in model.predict([(q["query"], c["content"]) for c in q["candidates"]])]
        seconds = round(time.perf_counter() - start, 3)
        out.append({"key": q["key"], "seconds": seconds,
                    "scores": {c["chunk_id"]: round(p, 4) for c, p in zip(q["candidates"], probs)}})
        print(q["key"], [round(p, 3) for p in probs], f"{seconds}s")
    (RESULTS / "rerank-E4c-bge-m3.json").write_text(json.dumps({"model": MODEL, "results": out}, ensure_ascii=False,
                                                               indent=1), encoding="utf-8")


def human_labels():
    with (RESULTS / "rerank-E4c-review.csv").open(encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))[1:]
    labels = {}
    for r in rows:
        key, cid = r[0].rsplit("/", 1)
        if r[3].strip() == "":
            raise SystemExit(f"사람 관련도가 비었다: {r[0]}")
        labels[(key, int(cid))] = int(r[3])
    return labels


def report(name, kept_by_key, labels, queries, seconds=None):
    """kept_by_key: 검색어 → 남긴 chunk_id 목록. 정답 기준은 관련도 2(근거가 됨)와 1 이상 두 가지."""
    line = [name]
    for need in (2, 1):
        kept = [(k, c) for k, cs in kept_by_key.items() for c in cs]
        good = sum(labels[x] >= need for x in kept)
        relevant = [(q["key"], c["chunk_id"]) for q in queries for c in q["candidates"] if labels[(q["key"], c["chunk_id"])] >= need]
        found = sum(x in set(kept) for x in relevant)
        line.append(f"≥{need}: 정밀도 {good}/{len(kept)}={good / len(kept):.2f}" if kept else f"≥{need}: 남긴 것 없음")
        line.append(f"재현율 {found}/{len(relevant)}={found / len(relevant):.2f}" if relevant else "")
    # 관련 청크(≥1)가 하나도 없는 검색어에서 전부 버렸는지
    empty = [q["key"] for q in queries if not any(labels[(q["key"], c["chunk_id"])] >= 1 for c in q["candidates"])]
    line.append(f"정답 없는 검색어 {len(empty)}개 중 전부 버림 {sum(not kept_by_key.get(k) for k in empty)}")
    line.append(f"관련 있는데 다 버림 {sum(not kept_by_key.get(q['key']) for q in queries if q['key'] not in empty)}")
    if seconds is not None:
        line.append(f"검색어당 {seconds:.2f}초")
    print(" | ".join(x for x in line if x))


def compare(filter_label="exaone"):
    queries, labels = load_candidates(), human_labels()
    base = {q["key"]: [c["chunk_id"] for c in q["candidates"] if c["similarity"] >= MIN_SIMILARITY][:TOP_K] for q in queries}
    report("A 지금(유사도≥0.50, 상위5)", base, labels, queries)
    report("  참고: 상위8 전부", {q["key"]: [c["chunk_id"] for c in q["candidates"]] for q in queries}, labels, queries)

    fpath = RESULTS / f"filter-E4c-{filter_label}.json"
    if fpath.exists():
        f = {r["key"]: r for r in json.loads(fpath.read_text(encoding="utf-8"))["results"]}
        secs = sum(r["seconds"] for r in f.values()) / len(f)
        report("B LLM 필터(상위8에서)", {k: r["kept"] for k, r in f.items()}, labels, queries, secs)
        report("B' A + LLM 필터", {k: [c for c in base[k] if c in f[k]["kept"]] for k in base}, labels, queries)
    else:
        print(f"({fpath.name} 없음: LLM 필터 생략)")

    rpath = RESULTS / "rerank-E4c-bge-m3.json"
    if rpath.exists():
        r = {x["key"]: x for x in json.loads(rpath.read_text(encoding="utf-8"))["results"]}
        secs = sum(x["seconds"] for x in r.values()) / len(r)
        for t in RERANK_THRESHOLDS:
            kept = {k: [c for c, s in sorted(x["scores"].items(), key=lambda y: -y[1]) if s >= t][:TOP_K] for k, x in r.items()}
            report(f"C 리랭커(점수≥{t}, 상위5)", {k: [int(c) for c in v] for k, v in kept.items()}, labels, queries, secs)
    else:
        print(f"({rpath.name} 없음: 리랭커 생략)")


if __name__ == "__main__":
    {"score": score, "compare": compare}[sys.argv[1]](*sys.argv[2:])
