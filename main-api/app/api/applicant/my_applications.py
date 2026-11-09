from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_applicant
from app.models.member import Member
from app.schemas.application_status import ApplicationStatusItem
from app.services.application_status_service import ApplicationStatusService

router = APIRouter(prefix="/api/applications", tags=["applications"])


@router.get("", response_model=list[ApplicationStatusItem])
async def list_my_applications(member: Member = Depends(require_applicant), db: AsyncSession = Depends(get_db)):
    """APP-012, APP-017 내 지원 현황. 지원자 본인 것만 보이고 관리자는 쓸 수 없다."""
    return await ApplicationStatusService(db).list_mine(member)
