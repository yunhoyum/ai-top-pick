"""API 오류 형식: {"code": "...", "message": "..."} (코드베이스 4.4)"""

from enum import Enum

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ErrorCode(str, Enum):
    EMAIL_DUPLICATED = "EMAIL_DUPLICATED"
    LOGIN_FAILED = "LOGIN_FAILED"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    FORBIDDEN = "FORBIDDEN"
    POSTING_NOT_FOUND = "POSTING_NOT_FOUND"
    POSTING_NOT_EDITABLE = "POSTING_NOT_EDITABLE"
    POSTING_INVALID = "POSTING_INVALID"
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    FILE_INVALID = "FILE_INVALID"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"


class AppError(Exception):
    def __init__(self, status_code: int, code: ErrorCode, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message


def register_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code.value, "message": exc.message},
        )
