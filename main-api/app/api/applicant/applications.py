from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_member, get_db, require_applicant
from app.models.member import Member
from app.schemas.application import ApplicationOut, EssaysIn, ResumeIn, SkillsIn
from app.services.application_service import ApplicationService

router = APIRouter(prefix="/api/postings/{posting_id}/application", tags=["applications"])


@router.get("", response_model=ApplicationOut)
async def get_application(
    posting_id: int, member: Member = Depends(get_current_member), db: AsyncSession = Depends(get_db)
):
    """지원서 열기. 지원자는 없으면 새로 만든다. 관리자는 저장할 수 없는 빈 화면을 미리 본다."""
    return await ApplicationService(db).get(member, posting_id)


@router.put("/resume", response_model=ApplicationOut)
async def save_resume(
    posting_id: int,
    req: ResumeIn,
    validate: bool = True,
    member: Member = Depends(require_applicant),
    db: AsyncSession = Depends(get_db),
):
    """APP-005 이력서 저장. 임시 저장은 validate=false"""
    return await ApplicationService(db).save_resume(member, posting_id, req, validate)


@router.put("/skills", response_model=ApplicationOut)
async def save_skills(
    posting_id: int,
    req: SkillsIn,
    validate: bool = True,
    member: Member = Depends(require_applicant),
    db: AsyncSession = Depends(get_db),
):
    """APP-006, APP-007 사용기술과 기술 적용 사례 저장"""
    return await ApplicationService(db).save_skills(member, posting_id, req, validate)


@router.put("/essays", response_model=ApplicationOut)
async def save_essays(
    posting_id: int,
    req: EssaysIn,
    validate: bool = True,
    member: Member = Depends(require_applicant),
    db: AsyncSession = Depends(get_db),
):
    """APP-008 자기소개서 저장"""
    return await ApplicationService(db).save_essays(member, posting_id, req, validate)


@router.post("/portfolio", response_model=ApplicationOut)
async def upload_portfolio(
    posting_id: int,
    file: UploadFile,
    member: Member = Depends(require_applicant),
    db: AsyncSession = Depends(get_db),
):
    """APP-009 포트폴리오(PDF) 등록. 이미 있으면 바꾼다."""
    return await ApplicationService(db).upload_portfolio(member, posting_id, file)


@router.delete("/portfolio", response_model=ApplicationOut)
async def delete_portfolio(
    posting_id: int, member: Member = Depends(require_applicant), db: AsyncSession = Depends(get_db)
):
    return await ApplicationService(db).delete_portfolio(member, posting_id)


@router.post("/submit", response_model=ApplicationOut)
async def submit_application(
    posting_id: int, member: Member = Depends(require_applicant), db: AsyncSession = Depends(get_db)
):
    """APP-011 서류 제출"""
    return await ApplicationService(db).submit(member, posting_id)
