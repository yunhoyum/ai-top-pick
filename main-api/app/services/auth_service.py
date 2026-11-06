import asyncio

from fastapi import Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ErrorCode
from app.core.security import (
    create_access_token,
    hash_password,
    set_auth_cookie,
    verify_password,
)
from app.domain.enums import Role
from app.models.member import Member
from app.repositories.member_repo import MemberRepo
from app.schemas.auth import LoginRequest, SignupRequest


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.members = MemberRepo(db)

    async def signup(self, req: SignupRequest) -> Member:
        """ADM-001, APP-001 회원가입"""
        if await self.members.get_by_email(req.email):
            raise self._duplicated()

        company_id = None
        if req.role == Role.ADMIN:
            company = await self.members.get_or_create_company(req.company_name.strip())
            company_id = company.company_id

        # bcrypt는 CPU를 쓰므로 이벤트 루프를 막지 않게 스레드에서 돌린다
        hashed = await asyncio.to_thread(hash_password, req.password)
        member = Member(
            company_id=company_id,
            role=req.role.value,
            name=req.name,
            email=req.email,
            password=hashed,
        )
        try:
            await self.members.create(member)
            await self.db.commit()
        except IntegrityError:
            # 동시에 같은 이메일로 가입한 경우 (email UNIQUE)
            await self.db.rollback()
            raise self._duplicated()
        return member

    async def login(self, req: LoginRequest, response: Response) -> Member:
        """ADM-002, APP-002 로그인"""
        member = await self.members.get_by_email(req.email)
        # 이메일·비밀번호·역할 중 무엇이 틀렸는지 알려 주지 않는다
        if (
            member is None
            or member.role != req.role.value
            or not await asyncio.to_thread(verify_password, req.password, member.password)
        ):
            raise AppError(401, ErrorCode.LOGIN_FAILED, "이메일 또는 비밀번호가 올바르지 않습니다.")
        set_auth_cookie(response, create_access_token(member.member_id, member.role))
        return member

    @staticmethod
    def _duplicated() -> AppError:
        return AppError(409, ErrorCode.EMAIL_DUPLICATED, "이미 가입된 이메일입니다.")
