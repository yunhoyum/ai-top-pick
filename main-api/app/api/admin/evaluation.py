from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin
from app.models.member import Member
from app.schemas.evaluation import OpinionIn, OpinionOut, RankingOut, ReportOut
from app.services.evaluation_service import EvaluationService

# 경로는 코드베이스 7.2를 따른다. {stage}는 아직 document만 있다 (면접 전형 평가는 면접 보고서 뒤)
router = APIRouter(prefix="/api/admin", tags=["admin-evaluation"])


@router.get("/postings/{posting_id}/stages/document/ranking", response_model=RankingOut)
async def get_document_ranking(posting_id: int, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """화면 17 서류 지원자 순위 (ADM-023)"""
    return await EvaluationService(db).get_ranking(admin, posting_id)


@router.get("/applications/{application_id}/stages/document/report", response_model=ReportOut)
async def get_document_report(application_id: int, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """화면 18 서류 전형 결과 보고서 (ADM-021)"""
    return await EvaluationService(db).get_report(admin, application_id)


@router.put("/applications/{application_id}/stages/document/opinion", response_model=OpinionOut)
async def save_document_opinion(
    application_id: int, body: OpinionIn, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """화면 17·18 관리자 의견 (ADM-024)"""
    return OpinionOut(opinion=await EvaluationService(db).save_opinion(admin, application_id, body.opinion))
