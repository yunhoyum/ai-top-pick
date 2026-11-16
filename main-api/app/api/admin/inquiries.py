from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin
from app.models.member import Member
from app.schemas.inquiry import InquiryDetail, InquiryItem
from app.services.inquiry_service import InquiryService

router = APIRouter(prefix="/api/admin/inquiries", tags=["admin-inquiries"])


@router.get("", response_model=list[InquiryItem])
async def list_inquiries(
    handling_status: str | None = None, posting_id: int | None = None,
    admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db),
):
    """화면 26 문의·예외 처리 목록 (ADM-026). 처리 상태 탭: AI 미처리, 관리자 대기, 관리자 처리 완료, AI 처리."""
    return await InquiryService(db).list_inquiries(admin, handling_status, posting_id)


@router.get("/{inquiry_id}", response_model=InquiryDetail)
async def get_inquiry(inquiry_id: int, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """화면 26-1 문의 상세 (ADM-026)."""
    return await InquiryService(db).get_inquiry(admin, inquiry_id)


@router.post("/{inquiry_id}/resume", response_model=InquiryDetail)
async def resume(inquiry_id: int, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """화면 26 '면접 재개' (ADM-041, SYS-012). 지원자는 내 지원 현황에서 '재접속 가능'을 본다."""
    return await InquiryService(db).resume_by_admin(admin, inquiry_id)
