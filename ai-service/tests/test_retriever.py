"""search_company_docs 테스트.

실제 DB(PC1 postgres)에 연결하지만 실제 doc_chunk는 건드리지 않는다.
같은 연결 안에 같은 이름의 임시 테이블을 만들면 PostgreSQL은 임시 테이블을 먼저 찾는다.
트랜잭션을 되돌리면 임시 테이블도 사라진다.
"""

import math
import re

import pytest
from sqlalchemy import create_engine, insert, text

from app.core.config import get_settings
from app.db.doc_chunk import EMBEDDING_DIM, DocChunk
from app.rag.retriever import search_company_docs

POSTING = 1
OTHER_POSTING = 2


def _vector(*axes: int) -> list[float]:
    """axes 방향 단위 벡터의 합을 길이 1로 맞춘 벡터."""
    v = [0.0] * EMBEDDING_DIM
    for a in axes:
        v[a] = 1.0
    norm = math.sqrt(len(axes))
    return [x / norm for x in v]


class FakeEmbedClient:
    """단어 하나를 토큰 하나로 본다. 글 속의 'q0', 'q1' 같은 단어가 벡터 방향을 정한다."""

    def __init__(self):
        self.embedded: list[str] = []

    def tokenize(self, texts):
        return [[(m.start(), m.end()) for m in re.finditer(r"\S+", t)] for t in texts]

    def embed(self, texts):
        self.embedded += texts
        return [_vector(*sorted({int(w[1:]) for w in re.findall(r"q\d+", t)})) for t in texts]


@pytest.fixture
def conn():
    engine = create_engine(get_settings().sqlalchemy_url)
    with engine.connect() as c:
        # 외래 키·CHECK는 복사되지 않는다. 테스트용 공고·문서 행이 필요 없다
        c.execute(text("CREATE TEMP TABLE doc_chunk (LIKE public.doc_chunk) ON COMMIT DROP"))
        c.execute(
            insert(DocChunk),
            [
                _row(1, POSTING, "결제 서버는 Redis 캐시를 쓴다.", _vector(0)),
                _row(2, POSTING, "배포는 Docker로 한다.", _vector(1)),
                _row(3, POSTING, "결제 서버 배포 절차.", _vector(0, 1)),
                _row(4, OTHER_POSTING, "다른 공고의 결제 문서.", _vector(0)),
            ],
        )
        yield c
        c.rollback()
    engine.dispose()


def _row(chunk_id, posting_id, content, embedding):
    return {
        "chunk_id": chunk_id,
        "posting_id": posting_id,
        "source_type": "프로젝트 문서",
        "source_id": 100 + chunk_id,
        "seq": 0,
        "content": content,
        "embedding": embedding,
    }


def _search(conn, texts, top_k=5, client=None):
    return search_company_docs(POSTING, texts, top_k, bind=conn, client=client or FakeEmbedClient())


def test_finds_closest_chunks_of_the_posting_only(conn):
    found = _search(conn, ["q0"], top_k=2)
    # 4번은 거리가 0이지만 다른 공고라 나오지 않는다
    assert [c.chunk_id for c in found] == [1, 3]
    assert found[0].similarity == pytest.approx(1.0)
    assert found[1].similarity == pytest.approx(1 / math.sqrt(2))
    assert found[0].content == "결제 서버는 Redis 캐시를 쓴다."


def test_merges_results_of_several_texts_keeping_highest_similarity(conn):
    found = _search(conn, ["q0", "q1"], top_k=3)
    # 3번은 두 검색어 모두에서 나오지만 한 번만 들어간다
    assert sorted(c.chunk_id for c in found) == [1, 2, 3]
    assert found[-1].chunk_id == 3


def test_drops_chunks_below_min_similarity(conn, monkeypatch):
    monkeypatch.setattr(get_settings(), "RAG_MIN_SIMILARITY", 0.5)
    # 2번은 q0과 직교해서 유사도가 0이다
    assert [c.chunk_id for c in _search(conn, ["q0"])] == [1, 3]


def test_long_text_is_split_before_embedding(conn, monkeypatch):
    monkeypatch.setattr(get_settings(), "QUERY_MAX_TOKENS", 4 + 2)
    client = FakeEmbedClient()
    found = _search(conn, ["q0 a b c\n\nq1 d e f"], top_k=2, client=client)
    # 문단마다 따로 임베딩한다. 나누지 않으면 두 주제가 섞인 3번만 가장 가깝게 나온다
    assert client.embedded == ["q0 a b c", "q1 d e f"]
    assert sorted(c.chunk_id for c in found) == [1, 2]


def test_blank_texts_are_not_searched(conn):
    client = FakeEmbedClient()
    assert _search(conn, ["", "  \n"], client=client) == []
    assert client.embedded == []


def test_posting_without_chunks_returns_empty(conn):
    found = search_company_docs(999, ["q0"], bind=conn, client=FakeEmbedClient())
    assert found == []
