import re

import pytest

from app.workers.chunking import SPECIAL_TOKENS, split_by_offsets


def _words(text):
    """공백으로 나눈 단어 하나를 토큰 하나로 본다 (embed-server /tokenize 대신)."""
    return [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]


def _split(text, max_tokens, overlap):
    return split_by_offsets(text, _words(text), max_tokens, overlap)


def test_short_text_is_one_chunk():
    assert _split("결제 서버는 Redis 캐시를 쓴다.", 512, 64) == ["결제 서버는 Redis 캐시를 쓴다."]


def test_empty_text_has_no_chunks():
    assert split_by_offsets("", [], 512, 64) == []


def test_long_paragraph_is_cut_at_limit_with_overlap():
    words = [f"w{i}" for i in range(30)]
    chunks = _split(" ".join(words), max_tokens=10 + SPECIAL_TOKENS, overlap=3)
    pieces = [c.split() for c in chunks]
    # 청크 본문은 특수 토큰 2개를 뺀 10토큰 이하다
    assert all(len(p) <= 10 for p in pieces)
    # 다음 청크는 앞 청크의 마지막 3토큰으로 시작한다
    for before, after in zip(pieces, pieces[1:]):
        assert after[:3] == before[-3:]
    # 빠진 단어가 없다
    assert pieces[0] + [w for p in pieces[1:] for w in p[3:]] == words


def test_chunk_ends_at_paragraph_break_when_possible():
    text = "a1 a2 a3 a4 a5 a6\n\nb1 b2 b3 b4 b5 b6\n\nc1 c2"
    chunks = _split(text, max_tokens=10 + SPECIAL_TOKENS, overlap=2)
    # 10토큰 안에서 가장 늦은 문단 경계(b1 앞)에서 끊는다
    assert chunks[0] == "a1 a2 a3 a4 a5 a6"
    assert chunks[1].startswith("a5 a6\n\nb1")


def test_overlap_must_be_shorter_than_limit():
    with pytest.raises(ValueError):
        _split("a b c", max_tokens=5, overlap=3)
