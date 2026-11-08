from pathlib import Path

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode


def resolve(path: str) -> Path:
    """STORAGE_ROOT 안의 경로로 바꾼다. 밖으로 벗어나는 경로는 막는다."""
    root = Path(get_settings().STORAGE_ROOT).resolve()
    full = (root / path).resolve()
    if root != full and root not in full.parents:
        raise ValueError("STORAGE_ROOT 밖의 경로입니다.")
    return full


async def read_pdf(upload: UploadFile) -> bytes:
    """확장자, MIME, 시작 바이트(%PDF), 크기를 확인하고 내용을 돌려준다."""
    name = (upload.filename or "").lower()
    if not name.endswith(".pdf") or upload.content_type != "application/pdf":
        raise AppError(422, ErrorCode.FILE_INVALID, "PDF 파일만 등록할 수 있습니다.")
    limit = get_settings().MAX_PDF_MB * 1024 * 1024
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise AppError(413, ErrorCode.FILE_TOO_LARGE, f"파일은 {get_settings().MAX_PDF_MB}MB 이하여야 합니다.")
    if not data.startswith(b"%PDF"):
        raise AppError(422, ErrorCode.FILE_INVALID, "PDF 파일만 등록할 수 있습니다.")
    return data


def save(path: str, data: bytes) -> None:
    full = resolve(path)
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(data)


def delete(path: str) -> None:
    resolve(path).unlink(missing_ok=True)
