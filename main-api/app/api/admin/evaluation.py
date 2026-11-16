from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin
from app.models.member import Member
from app.schemas.evaluation import (
    InterviewSourceOut,
    OpinionIn,
    OpinionOut,
    PassIn,
    PassOut,
    RankingOut,
    ReportOut,
    SourceDocumentsOut,
)
from app.services.evaluation_service import EvaluationService

# 경로는 코드베이스 7.2를 따른다. 서류는 stages/document, 면접은 stages/interview
router = APIRouter(prefix="/api/admin", tags=["admin-evaluation"])


@router.get("/postings/{posting_id}/stages/document/ranking", response_model=RankingOut)
async def get_document_ranking(posting_id: int, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """화면 17·20 서류 지원자 순위 (ADM-023)"""
    return await EvaluationService(db).get_ranking(admin, posting_id)


@router.post("/postings/{posting_id}/stages/document/pass", response_model=PassOut)
async def confirm_document_pass(
    posting_id: int, body: PassIn, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """화면 20 서류 합격자 확정 (ADM-025)"""
    return await EvaluationService(db).confirm_pass(admin, posting_id, body.application_ids)


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


@router.get("/applications/{application_id}/documents", response_model=SourceDocumentsOut)
async def get_source_documents(application_id: int, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """화면 19 지원자 자료 원본: 이력서, 자기소개서 (ADM-022)"""
    return await EvaluationService(db).get_source_documents(admin, application_id)


@router.get("/applications/{application_id}/portfolio/file")
async def get_portfolio_file(application_id: int, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """화면 19 포트폴리오 PDF. 내려받지 않고 브라우저에서 바로 연다 (프로젝트 문서 보기와 같다)."""
    path, file_name = await EvaluationService(db).get_portfolio_file(admin, application_id)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=file_name,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff"},
    )


# ---------- 면접 전형 평가 (화면 27~30) ----------
INTERVIEW = "면접"


@router.get("/postings/{posting_id}/stages/interview/ranking", response_model=RankingOut)
async def get_interview_ranking(posting_id: int, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """화면 27·30 면접 지원자 순위 (ADM-029). 꼬리질문 횟수를 함께 보인다"""
    return await EvaluationService(db).get_ranking(admin, posting_id, INTERVIEW)


@router.post("/postings/{posting_id}/stages/interview/pass", response_model=PassOut)
async def confirm_interview_pass(
    posting_id: int, body: PassIn, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """화면 30 면접 합격자 확정 (ADM-031). 공고가 '마감'이 된다"""
    return await EvaluationService(db).confirm_pass(admin, posting_id, body.application_ids, INTERVIEW)


@router.get("/applications/{application_id}/stages/interview/report", response_model=ReportOut)
async def get_interview_report(application_id: int, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """화면 28 면접 전형 결과 보고서 (ADM-027). 질문별 결과 포함 (SYS-010)"""
    return await EvaluationService(db).get_report(admin, application_id, INTERVIEW)


@router.put("/applications/{application_id}/stages/interview/opinion", response_model=OpinionOut)
async def save_interview_opinion(
    application_id: int, body: OpinionIn, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """화면 27·28 관리자 의견 (ADM-030)"""
    return OpinionOut(opinion=await EvaluationService(db).save_opinion(admin, application_id, body.opinion, INTERVIEW))


@router.get("/applications/{application_id}/interview", response_model=InterviewSourceOut)
async def get_interview_source(application_id: int, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """화면 29 면접 자료 원본: 질문 목록, 답변 기록(STT 보정문·인식 원문) (ADM-028)"""
    return await EvaluationService(db).get_interview_source(admin, application_id)


@router.get("/answers/{answer_id}/video")
async def get_answer_video(answer_id: int, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """화면 29 답변 영상(webm). 브라우저가 Range 요청으로 나눠 받는다"""
    path = await EvaluationService(db).get_answer_video(admin, answer_id)
    return FileResponse(path, media_type="video/webm", headers={"X-Content-Type-Options": "nosniff"})
