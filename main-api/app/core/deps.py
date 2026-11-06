from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ErrorCode
from app.core.security import AUTH_COOKIE, decode_access_token
from app.db.session import AsyncSessionLocal
from app.domain.enums import Role
from app.models.member import Member
from app.repositories.member_repo import MemberRepo


async def get_db() -> AsyncIterator[AsyncSession]:
    """요청마다 DB 세션을 연다."""
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_member(request: Request, db: AsyncSession = Depends(get_db)) -> Member:
    """access_token 쿠키의 JWT로 현재 회원을 찾는다. 없거나 잘못되었거나 만료되면 401."""
    token = request.cookies.get(AUTH_COOKIE)
    if not token:
        raise AppError(401, ErrorCode.UNAUTHENTICATED, "로그인이 필요합니다.")
    payload = decode_access_token(token)
    member = await MemberRepo(db).get_by_id(payload.member_id)
    if member is None:
        # 토큰은 유효하지만 회원이 삭제된 경우
        raise AppError(401, ErrorCode.UNAUTHENTICATED, "로그인이 필요합니다.")
    return member


def _forbidden() -> AppError:
    return AppError(403, ErrorCode.FORBIDDEN, "접근 권한이 없습니다.")


async def require_admin(member: Member = Depends(get_current_member)) -> Member:
    """관리자만 통과한다. 다른 역할이면 403."""
    if member.role != Role.ADMIN.value:
        raise _forbidden()
    return member


async def require_applicant(member: Member = Depends(get_current_member)) -> Member:
    """지원자만 통과한다. 다른 역할이면 403."""
    if member.role != Role.APPLICANT.value:
        raise _forbidden()
    return member
