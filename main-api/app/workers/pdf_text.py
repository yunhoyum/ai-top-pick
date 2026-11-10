"""PDF 텍스트 추출 (PyMuPDF, 벡터 DB 설계서 12).

PDF는 문단을 모르고 줄만 안다. 그래서 줄의 위치로 문단을 다시 만든다.
- 같은 높이에 있는 줄 조각(글머리표 '•'와 본문 등)은 한 줄로 합친다.
- 위아래 간격이 줄 높이의 30%보다 좁고 글자 크기가 같으면 줄바꿈으로 이어진 같은 문단으로 본다.
  글머리표('•')나 번호('1.')로 시작하는 줄은 늘 새 문단이다.
- 여러 쪽의 위·아래 여백에 되풀이되는 줄(머리글, 쪽 번호)은 뺀다.
"""

import logging
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pymupdf

log = logging.getLogger(__name__)

# 줄 사이 간격이 줄 높이 × 이 값보다 좁으면 같은 문단이다
WRAP_GAP_RATIO = 0.3
# 글자 크기 차이가 이보다 크면 다른 문단이다 (굵은 소제목 등)
SIZE_TOLERANCE = 0.2
_LIST_ITEM = re.compile(r"^(•|\d+\.\s)")
# 쪽 높이의 위·아래 이 비율 안에 있는 줄만 머리글·바닥글 후보로 본다
MARGIN_RATIO = 0.1
# 이 쪽 수 이상에서 되풀이되어야 머리글·바닥글로 본다
MIN_REPEATED_PAGES = 3


@dataclass
class _Line:
    text: str
    top: float
    bottom: float
    size: float


def extract_text(path: Path) -> str:
    """문단을 빈 줄로 잇는다. 문단이 청크 분할의 경계 후보가 된다.
    텍스트가 없는 페이지(이미지만 있는 페이지)는 건너뛴다. 처리 방식은 아직 정하지 않았다 (벡터 DB 설계서 4.4)."""
    with pymupdf.open(path) as doc:
        pages = [(page.rect.height, _lines(page)) for page in doc]

    repeated = _repeated_margin_lines(pages)
    paragraphs: list[str] = []
    for number, (height, lines) in enumerate(pages, start=1):
        lines = [l for l in lines if not (_in_margin(l, height) and _key(l.text) in repeated)]
        if not lines:
            log.warning("%s %d쪽에 텍스트가 없어 건너뜁니다", path.name, number)
            continue
        paragraphs += _paragraphs(lines)
    return "\n\n".join(paragraphs)


def _lines(page) -> list[_Line]:
    """쪽의 줄을 위에서 아래로. 같은 높이의 조각은 왼쪽부터 이어 한 줄로 만든다."""
    pieces = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:  # 0이 텍스트, 1이 이미지다
            continue
        for line in block["lines"]:
            text = "".join(span["text"] for span in line["spans"]).strip()
            if text:
                x0, top, _, bottom = line["bbox"]
                pieces.append((top, x0, bottom, text, max(span["size"] for span in line["spans"])))
    pieces.sort()

    lines: list[_Line] = []
    for top, _, bottom, text, size in pieces:
        if lines and abs(top - lines[-1].top) < 1:
            lines[-1].text += " " + text
            lines[-1].size = max(lines[-1].size, size)
        else:
            lines.append(_Line(text, top, bottom, size))
    return lines


def _paragraphs(lines: list[_Line]) -> list[str]:
    paragraphs = [lines[0].text]
    for prev, line in zip(lines, lines[1:]):
        wrapped = (
            line.top - prev.bottom < (prev.bottom - prev.top) * WRAP_GAP_RATIO
            and abs(line.size - prev.size) <= SIZE_TOLERANCE
            and not _LIST_ITEM.match(line.text)
        )
        if wrapped:
            paragraphs[-1] = _join_wrapped(paragraphs[-1], line.text)
        else:
            paragraphs.append(line.text)
    return paragraphs


def _join_wrapped(before: str, after: str) -> str:
    """줄바꿈 자리의 띄어쓰기는 PDF에 남지 않는다. 한글 사이면 붙이고(글자 단위 줄바꿈), 아니면 띄운다.
    한글 낱말 사이에서 줄이 바뀐 경우는 띄어쓰기 하나를 잃는다."""
    if _is_hangul(before[-1]) and _is_hangul(after[0]):
        return before + after
    return before + " " + after


def _is_hangul(ch: str) -> bool:
    return "가" <= ch <= "힣"


def _key(text: str) -> str:
    """쪽마다 숫자만 다른 줄(쪽 번호 등)을 같은 줄로 본다."""
    return re.sub(r"\d+", "#", text)


def _in_margin(line: _Line, height: float) -> bool:
    return line.bottom < height * MARGIN_RATIO or line.top > height * (1 - MARGIN_RATIO)


def _repeated_margin_lines(pages: list[tuple[float, list[_Line]]]) -> set[str]:
    counts = Counter(
        key for height, lines in pages for key in {_key(l.text) for l in lines if _in_margin(l, height)}
    )
    needed = max(MIN_REPEATED_PAGES, len(pages) // 2)
    return {key for key, n in counts.items() if n >= needed}
