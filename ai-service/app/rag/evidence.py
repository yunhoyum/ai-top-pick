"""근거 후보 문장 만들기 (벡터 DB 설계서 8.4의 1~2단계, RAG 설계서 3.1의 ③④)."""

import re
from dataclasses import dataclass

from app.rag.retriever import Chunk

# 마침표·물음표·느낌표 뒤 공백, 또는 줄바꿈에서 문장을 나눈다 (벡터 DB 설계서 8.4). 'v1.2', '0.93'은 나누지 않는다
_SENTENCE_BREAK = re.compile(r"(?<=[.?!])\s+|\n+")
_LIST_NUMBER = re.compile(r"\d+\.")


@dataclass(frozen=True)
class NumberedSentence:
    id: str  # "후보 순번-문장 순번", 예: "1-2"
    text: str
    chunk: Chunk


def merge_contexts(*contexts: list[Chunk]) -> list[Chunk]:
    """chunk_id로 합치고 같은 청크는 가장 높은 유사도를 남긴다. 유사도 순으로 돌려준다."""
    best: dict[int, Chunk] = {}
    for chunks in contexts:
        for chunk in chunks:
            kept = best.get(chunk.chunk_id)
            if kept is None or chunk.similarity > kept.similarity:
                best[chunk.chunk_id] = chunk
    return sorted(best.values(), key=lambda c: c.similarity, reverse=True)


def split_sentences(text: str) -> list[str]:
    """번호 목록 '10. 문장'은 '10.' 뒤 공백에서도 나뉜다. 번호만 남은 조각은 뒤 문장에 붙인다 (RAG 설계서 5.5 P9)."""
    sentences: list[str] = []
    for piece in (s.strip() for s in _SENTENCE_BREAK.split(text)):
        if not piece:
            continue
        if sentences and _LIST_NUMBER.fullmatch(sentences[-1]):
            sentences[-1] = f"{sentences[-1]} {piece}"
        else:
            sentences.append(piece)
    return sentences


def number_sentences(
    chunks: list[Chunk], start: int = 1, already: list[NumberedSentence] | None = None
) -> list[NumberedSentence]:
    """청크의 문장을 원래 순서대로 번호를 붙인다. 청크 겹침으로 이미 나온 문장은 다시 넣지 않는다.
    start, already: 앞 목록에 이어 붙일 때 후보 순번을 이어 매기고 앞 목록에 있는 문장은 건너뛴다."""
    seen: set[str] = {s.text for s in already or []}
    numbered: list[NumberedSentence] = []
    for i, chunk in enumerate(chunks, start=start):
        for j, sentence in enumerate(split_sentences(chunk.content), start=1):
            if sentence in seen:
                continue
            seen.add(sentence)
            numbered.append(NumberedSentence(f"{i}-{j}", sentence, chunk))
    return numbered
