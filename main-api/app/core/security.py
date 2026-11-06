from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Response

from app.core.config import get_settings

AUTH_COOKIE = "access_token"


def hash_password(raw: str) -> str:
    """비밀번호를 bcrypt로 해시한다."""
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()


def verify_password(raw: str, hashed: str) -> bool:
    """비밀번호를 해시와 비교한다."""
    return bcrypt.checkpw(raw.encode(), hashed.encode())


def create_access_token(member_id: int, role: str) -> str:
    """JWT를 만든다. 회원 ID와 역할을 클레임에 넣는다."""
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(member_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=s.JWT_EXPIRE_MIN),
    }
    return jwt.encode(payload, s.JWT_SECRET, algorithm=s.JWT_ALGORITHM)


def set_auth_cookie(response: Response, token: str) -> None:
    """JWT를 HttpOnly 쿠키로 내려준다 (코드베이스 4.5). HTTPS로 운영하면 secure=True를 더한다."""
    response.set_cookie(
        AUTH_COOKIE,
        token,
        max_age=get_settings().JWT_EXPIRE_MIN * 60,
        httponly=True,
        samesite="lax",
        path="/",
    )
