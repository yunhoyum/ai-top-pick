"""WebSocket 인증 (코드베이스 1. main-api 8장, 본문 4.5). 연결 요청에 실린 access_token 쿠키의 JWT로 회원을 찾는다."""

from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import AUTH_COOKIE, decode_access_token
from app.domain.enums import Role
from app.models.member import Member
from app.repositories.member_repo import MemberRepo


async def authenticate_handshake(ws: WebSocket, db: AsyncSession) -> Member | None:
    """지원자 회원을 돌려준다. 쿠키가 없거나, 토큰이 틀리거나 만료됐거나, 지원자가 아니면 None."""
    token = ws.cookies.get(AUTH_COOKIE)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except AppError:
        return None
    member = await MemberRepo(db).get_by_id(payload.member_id)
    return member if member is not None and member.role == Role.APPLICANT.value else None
