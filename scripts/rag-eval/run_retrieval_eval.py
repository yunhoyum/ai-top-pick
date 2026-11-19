"""검색 평가 (RAG 설계서 5.3의 검색 지표: Recall@k, MRR, nDCG@5, 유사도 분포·분리도). ai-service 이미지에서 실행한다.

먼저 index_eval_posting.py로 공고를 색인한다. 필요한 컨테이너: postgres, embed-server.

final_project 폴더에서:
  docker run --rm --network pc1_default --env-file pc1/.env \
    -v "$(pwd)/ai-service:/src" -v "$(pwd)/scripts/rag-eval:/eval" -w /src pc2-ai-service:latest \
    python /eval/run_retrieval_eval.py <공고 ID> [실험 ID]
청크 크기를 바꿔 색인한 공고는 검색어 분할 길이도 같게 준다: docker run 뒤에 -e QUERY_MAX_TOKENS=128

결과는 results/<실험 ID>.json에 저장한다.
"""

import json
import math
import re
import statistics
import sys
import time
from pathlib import Path

sys.path[:0] = ["/src"]

from app.clients.embed import EmbedClient
from app.core.config import get_settings
from app.rag.retriever import search_company_docs

K = 5
# 청크가 작아지면 같은 k로 LLM에 넘기는 내용이 줄어든다. 큰 k도 함께 본다
K_WIDE = 10
# 정답 청크가 몇 위인지 보려고 공고의 청크를 모두 가져온다
ALL_CHUNKS = 10_000
# 결과가 비어야 하는 검색어. ㉡은 4단계 LLM 판정으로 확인하므로 검색 평가에서 뺀다
EMPTY_EXPECTED = {"관계없음", "㉠"}
THRESHOLDS = [round(0.30 + 0.05 * i, 2) for i in range(9)]


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _has_gold(chunk: str, gold: list[str]) -> bool:
    """청크가 gold 문장을 담으면 정답이다. 청크 경계에서 잘린 문장은 절반 이상을 담은 쪽을 정답으로 본다.

    잘린 두 조각 중 한쪽은 반드시 절반 이상이므로, 청크를 작게 나눠도 모든 gold 문장을 찾을 수 있다.
    """
    for g in gold:
        half = (len(g) + 1) // 2
        if g in chunk or any(chunk.endswith(g[:n]) or chunk.startswith(g[-n:]) for n in range(half, len(g))):
            return True
    return False


def _ndcg(relevant: list[bool], k: int) -> float:
    """정답 청크를 관련도 1로 보는 nDCG@k. 이상적인 순위는 공고 전체 청크의 정답 수로 정한다."""
    dcg = sum(1 / math.log2(i + 2) for i, r in enumerate(relevant[:k]) if r)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(sum(relevant), k)))
    return dcg / ideal if ideal else 0.0


def evaluate(posting_id: int) -> list[dict]:
    settings = get_settings()
    # 유사도 분포를 보려고 거르지 않는다. min_similarity는 이 결과로 정한다
    settings.RAG_MIN_SIMILARITY = -1.0
    queries = json.loads(Path("/eval/rag_eval_set.json").read_text(encoding="utf-8"))["queries"]
    client = EmbedClient()
    rows = []
    for q in queries:
        started = time.perf_counter()
        found = search_company_docs(posting_id, [q["query"]], top_k=ALL_CHUNKS)
        ms = (time.perf_counter() - started) * 1000
        gold = [_norm(g) for g in q["gold"]]
        relevant = [bool(gold) and _has_gold(_norm(c.content), gold) for c in found]
        rank = next((i + 1 for i, r in enumerate(relevant) if r), None)
        tokens = [len(o) for o in client.tokenize([c.content for c in found[:K_WIDE]])]
        rows.append(
            {
                "id": q["id"],
                "kind": q["kind"],
                "expect": q["expect"],
                "has_gold": bool(gold),
                "gold_rank": rank,
                "gold_similarity": found[rank - 1].similarity if rank else None,
                "gold_chunks": sum(relevant),
                f"ndcg_at_{K}": _ndcg(relevant, K) if gold else None,
                "top1_similarity": found[0].similarity,
                "top1_seq": found[0].seq,
                "top_seqs": [c.seq for c in found[:K]],
                f"tokens_top{K}": sum(tokens[:K]),
                f"tokens_top{K_WIDE}": sum(tokens),
                "chunks": len(found),
                "ms": round(ms),
            }
        )
    return rows


def report(rows: list[dict]) -> dict:
    gold_rows = [r for r in rows if r["has_gold"]]
    empty_rows = [r for r in rows if r["expect"] in EMPTY_EXPECTED]

    print(f"{'ID':<4} {'종류':<6} {'기대':<14} 정답순위 정답유사도 1위유사도 상위{K}청크(seq)")
    for r in rows:
        rank = r["gold_rank"] if r["has_gold"] else "-"
        gold_sim = f"{r['gold_similarity']:.3f}" if r["gold_similarity"] is not None else "  -  "
        print(f"{r['id']:<4} {r['kind']:<6} {r['expect']:<14} {rank!s:>6} {gold_sim:>9} {r['top1_similarity']:>8.3f} {r['top_seqs']}")

    def recall(k: int) -> float:
        return sum((r["gold_rank"] or 10**9) <= k for r in gold_rows) / len(gold_rows)

    recall_1, recall_3, recall_k, recall_wide = recall(1), recall(3), recall(K), recall(K_WIDE)
    mrr = statistics.mean(1 / r["gold_rank"] if r["gold_rank"] else 0.0 for r in gold_rows)
    ndcg = statistics.mean(r[f"ndcg_at_{K}"] for r in gold_rows)
    misses = [r["id"] for r in gold_rows if (r["gold_rank"] or 10**9) > K]
    print(f"\n청크 수 {rows[0]['chunks']}, 정답 있는 검색어 {len(gold_rows)}개, 결과가 비어야 하는 검색어 {len(empty_rows)}개")
    print(f"Recall@1 {recall_1:.1%}  @3 {recall_3:.1%}  @{K} {recall_k:.1%}  @{K_WIDE} {recall_wide:.1%}  놓친 검색어(@{K}) {misses}")
    print(f"MRR {mrr:.3f}  nDCG@{K} {ndcg:.3f}")

    gold_sims = [r["gold_similarity"] for r in gold_rows if r["gold_similarity"] is not None]
    empty_sims = [r["top1_similarity"] for r in empty_rows]
    # 양수면 min_similarity 하나로 정답과 비어야 할 검색어를 완전히 가를 수 있다
    margin = min(gold_sims) - max(empty_sims)
    print(f"정답 청크 유사도      최소 {min(gold_sims):.3f} 중앙 {statistics.median(gold_sims):.3f} 최대 {max(gold_sims):.3f}")
    print(f"비어야 할 검색어 1위   최소 {min(empty_sims):.3f} 중앙 {statistics.median(empty_sims):.3f} 최대 {max(empty_sims):.3f}")
    print(f"분리도(정답 최소 − 비어야 할 최대) {margin:+.3f}, 중앙값 차 {statistics.median(gold_sims) - statistics.median(empty_sims):+.3f}")

    tokens_k = statistics.median(r[f"tokens_top{K}"] for r in rows)
    tokens_wide = statistics.median(r[f"tokens_top{K_WIDE}"] for r in rows)
    print(f"상위 청크 토큰 합(중앙) top{K} {tokens_k:.0f}, top{K_WIDE} {tokens_wide:.0f}")

    print(f"\nmin_similarity 후보별: Recall@{K} (정답 청크가 {K}위 안이고 기준 이상) / 비어야 할 검색어 중 실제로 빈 비율")
    by_threshold = []
    for t in THRESHOLDS:
        kept = sum((r["gold_rank"] or 10**9) <= K and r["gold_similarity"] >= t for r in gold_rows) / len(gold_rows)
        empty_ok = sum(s < t for s in empty_sims) / len(empty_sims)
        by_threshold.append({"min_similarity": t, "recall_at_k": kept, "empty_correct": empty_ok})
        print(f"  {t:.2f}: {kept:6.1%} / {empty_ok:6.1%}")

    ms = [r["ms"] for r in rows]
    print(f"\n검색 시간(임베딩 포함) 중앙 {statistics.median(ms):.0f} ms, 최대 {max(ms)} ms")
    return {
        "chunks": rows[0]["chunks"],
        "recall_at_1": recall_1,
        "recall_at_3": recall_3,
        f"recall_at_{K}": recall_k,
        f"recall_at_{K_WIDE}": recall_wide,
        "mrr": mrr,
        f"ndcg_at_{K}": ndcg,
        "misses": misses,
        "gold_min_similarity": min(gold_sims),
        "empty_max_similarity": max(empty_sims),
        "margin": margin,
        f"median_tokens_top{K}": tokens_k,
        f"median_tokens_top{K_WIDE}": tokens_wide,
        "by_threshold": by_threshold,
        "median_ms": statistics.median(ms),
    }


if __name__ == "__main__":
    posting_id = int(sys.argv[1])
    experiment = sys.argv[2] if len(sys.argv) > 2 else "E0"
    rows = evaluate(posting_id)
    summary = report(rows)
    out = Path("/eval/results") / f"{experiment}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(
        json.dumps({"experiment": experiment, "posting_id": posting_id, "summary": summary, "rows": rows},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"저장: {out}")
