"""내부 API 인증. 모든 /internal 요청의 X-Internal-Token을 검사한다 (ai-service 2, 아키텍처 4.1-1)."""

import hmac

from fastapi import Header, HTTPException

from app.core.config import get_settings


def verify_internal_token(x_internal_token: str | None = Header(default=None)) -> None:
    if not x_internal_token or not hmac.compare_digest(x_internal_token, get_settings().INTERNAL_TOKEN):
        raise HTTPException(status_code=401, detail="내부 토큰이 맞지 않습니다.")
