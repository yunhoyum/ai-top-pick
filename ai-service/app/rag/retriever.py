"""회사 문서 검색 (벡터 DB 설계서 8장)."""

from dataclasses import dataclass

from sqlalchemy import Connection, Engine, select
from sqlalchemy.orm import Session

from app.clients.embed import EmbedClient
from app.core.config import get_settings
from app.db.doc_chunk import DocChunk
from app.db.session import get_engine
from app.rag.chunking import split_by_offsets


@dataclass(frozen=True)
class Chunk:
    chunk_id: int
    source_type: str
    source_id: int
    seq: int
    content: str
    similarity: float


def search_company_docs(
    posting_id: int,
    texts: list[str],
    top_k: int | None = None,
    *,
    bind: Engine | Connection | None = None,
    client: EmbedClient | None = None,
) -> list[Chunk]:
    """그 공고의 회사 문서 청크 중 texts와 가까운 것을 유사도 순으로 최대 top_k개 돌려준다.

    1. 긴 글은 나눈다 2. 한 번에 임베딩한다 3. 벡터마다 상위 top_k개를 찾는다
    4. chunk_id로 합치고 가장 높은 유사도를 남긴다 5. min_similarity 미만을 뺀다 6. 상위 top_k개
    """
    settings = get_settings()
    top_k = top_k or settings.RAG_TOP_K
    client = client or EmbedClient()

    queries = _split_queries(texts, client, settings.QUERY_MAX_TOKENS)
    if not queries:
        return []
    vectors = client.embed(queries)

    best: dict[int, Chunk] = {}
    with Session(bind or get_engine()) as db:
        for vector in vectors:
            distance = DocChunk.embedding.cosine_distance(vector)
            rows = db.execute(
                select(
                    DocChunk.chunk_id,
                    DocChunk.source_type,
                    DocChunk.source_id,
                    DocChunk.seq,
                    DocChunk.content,
                    (1 - distance).label("similarity"),
                )
                .where(DocChunk.posting_id == posting_id)
                # 거리 오름차순으로 둬야 나중에 벡터 인덱스를 둘 때 인덱스를 탄다 (벡터 DB 설계서 8.2)
                .order_by(distance)
                .limit(top_k)
            ).all()
            for row in rows:
                chunk = Chunk(*row)
                kept = best.get(chunk.chunk_id)
                if kept is None or chunk.similarity > kept.similarity:
                    best[chunk.chunk_id] = chunk

    found = [c for c in best.values() if c.similarity >= settings.RAG_MIN_SIMILARITY]
    return sorted(found, key=lambda c: c.similarity, reverse=True)[:top_k]


def _split_queries(texts: list[str], client: EmbedClient, max_tokens: int) -> list[str]:
    """검색어를 청크 최대 길이 이하로 나눈다. 겹침은 회사 문서에만 쓴다 (벡터 DB 설계서 4.2)."""
    # embed-server는 공백뿐인 글을 받지 않는다
    texts = [t for t in texts if t.strip()]
    if not texts:
        return []
    offsets = client.tokenize(texts)
    return [
        piece
        for text, text_offsets in zip(texts, offsets)
        for piece in split_by_offsets(text, text_offsets, max_tokens, overlap=0)
    ]
