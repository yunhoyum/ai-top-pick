from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.schemas.auth import LoginRequest, MemberOut, SignupRequest
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=MemberOut, status_code=201)
async def signup(req: SignupRequest, db: AsyncSession = Depends(get_db)):
    """ADM-001, APP-001 회원가입"""
    return await AuthService(db).signup(req)


@router.post("/login", response_model=MemberOut)
async def login(req: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    """ADM-002, APP-002 로그인. JWT는 본문이 아니라 HttpOnly 쿠키로 내려준다."""
    return await AuthService(db).login(req, response)
