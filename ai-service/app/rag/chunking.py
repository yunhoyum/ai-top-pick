"""긴 검색어 분할 (벡터 DB 설계서 8.1). main-api app/workers/chunking.py와 같은 코드다.

worker가 회사 문서를 자른 규칙으로 검색어도 자른다. 한쪽을 고치면 다른 쪽도 고친다.
문단 단위로 나눈 뒤 최대 길이 안에서 이어 붙인다. 길이는 KURE-v1 토큰으로 센다.
토큰 위치는 embed-server /tokenize가 준다.
"""

import re

# 임베딩 입력에는 시작·끝 특수 토큰 2개가 붙는다. 청크 본문은 그만큼 짧아야 잘리지 않는다
SPECIAL_TOKENS = 2

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


def split_by_offsets(
    text: str, offsets: list[tuple[int, int]], max_tokens: int, overlap: int
) -> list[str]:
    """토큰 위치(offsets)로 text를 청크로 나눈다.

    청크마다 최대 max_tokens − 2 토큰이다. 끝은 가능하면 문단 경계에 맞춘다.
    문단 하나가 너무 길면 토큰 경계에서 자른다. 다음 청크는 앞 청크의 마지막 overlap 토큰부터 시작한다.
    """
    limit = max_tokens - SPECIAL_TOKENS
    if overlap >= limit:
        raise ValueError("겹침 길이는 청크 최대 길이보다 짧아야 합니다.")
    n = len(offsets)
    if n == 0:
        return []

    # 문단이 시작하는 토큰 번호. 앞 토큰과 이 토큰 사이에 빈 줄이 있으면 새 문단이다
    paragraph_starts = {
        i for i in range(1, n) if _PARAGRAPH_BREAK.search(text, offsets[i - 1][1], offsets[i][0])
    }

    chunks: list[str] = []
    start = 0
    while True:
        end = min(start + limit, n)
        if end < n:
            # 겹침보다 뒤에 있는 문단 경계 중 가장 늦은 곳에서 끊는다. 없으면 길이 한도에서 자른다
            breaks = [p for p in paragraph_starts if start + overlap < p <= end]
            if breaks:
                end = max(breaks)
        chunks.append(text[offsets[start][0] : offsets[end - 1][1]].strip())
        if end >= n:
            return chunks
        start = end - overlap
