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
    # 출제 문제 개수가 이미 등록한 기업 질문 수보다 작다 (ADM-008, ADM-009)
    QUESTION_COUNT_TOO_LOW = "QUESTION_COUNT_TOO_LOW"
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    FILE_INVALID = "FILE_INVALID"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    # 서류 접수 중이 아닌 공고에는 지원서를 만들거나 저장할 수 없다 (APP-004)
    APPLICATION_CLOSED = "APPLICATION_CLOSED"
    # 이미 제출한 지원서는 고칠 수 없다
    APPLICATION_SUBMITTED = "APPLICATION_SUBMITTED"
    APPLICATION_INVALID = "APPLICATION_INVALID"


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
