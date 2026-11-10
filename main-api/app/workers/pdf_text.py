"""PDF 텍스트 추출 (PyMuPDF, 벡터 DB 설계서 12)."""

import logging
from pathlib import Path

import pymupdf

log = logging.getLogger(__name__)


def extract_text(path: Path) -> str:
    """페이지 순서대로 텍스트 블록을 뽑아 빈 줄로 잇는다. 블록이 문단 경계가 된다 (청크 분할이 문단 단위로 나눈다).
    텍스트가 없는 페이지(이미지만 있는 페이지)는 건너뛴다. 처리 방식은 아직 정하지 않았다 (벡터 DB 설계서 4.4)."""
    blocks: list[str] = []
    with pymupdf.open(path) as doc:
        for page in doc:
            # (x0, y0, x1, y1, 텍스트, 블록 번호, 블록 종류). 종류 0이 텍스트, 1이 이미지다
            texts = [b[4].strip() for b in page.get_text("blocks", sort=True) if b[6] == 0]
            texts = [t for t in texts if t]
            if not texts:
                log.warning("%s %d쪽에 텍스트가 없어 건너뜁니다", path.name, page.number + 1)
            blocks += texts
    return "\n\n".join(blocks)
