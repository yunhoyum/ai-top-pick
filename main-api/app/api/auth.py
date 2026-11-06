from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.schemas.auth import MemberOut, SignupRequest
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=MemberOut, status_code=201)
async def signup(req: SignupRequest, db: AsyncSession = Depends(get_db)):
    """ADM-001, APP-001 회원가입"""
    return await AuthService(db).signup(req)
