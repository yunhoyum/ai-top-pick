from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_applicant
from app.models.member import Member
from app.schemas.interview import EnterSessionRequest, InterviewGuide, SessionOut, VideoOut
from app.services.interview_service import InterviewService

router = APIRouter(prefix="/api/applications/{application_id}/interview", tags=["interview"])


@router.get("/guide", response_model=InterviewGuide)
async def get_guide(application_id: int, member: Member = Depends(require_applicant), db: AsyncSession = Depends(get_db)):
    """APP-014, APP-018 화면 22 AI 화상 면접 안내사항."""
    return await InterviewService(db).get_guide(member, application_id)


@router.post("/sessions", response_model=SessionOut)
async def enter_session(
    application_id: int, req: EnterSessionRequest,
    member: Member = Depends(require_applicant), db: AsyncSession = Depends(get_db),
):
    """APP-015 화면 23 기술적 테스트를 마치고 응시에 들어간다."""
    return await InterviewService(db).enter_session(member, application_id, req.camera_ok, req.mic_ok)


video_router = APIRouter(prefix="/api/interview/sessions/{session_id}", tags=["interview"])


@video_router.post("/questions/{question_id}/video", response_model=VideoOut)
async def upload_answer_video(
    session_id: int, question_id: int, file: UploadFile,
    member: Member = Depends(require_applicant), db: AsyncSession = Depends(get_db),
):
    """APP-016 화면 24 답변 영상. 답변이 끝나면 브라우저가 올린다 (아키텍처 7-7)."""
    return await InterviewService(db).save_answer_video(member, session_id, question_id, file)
