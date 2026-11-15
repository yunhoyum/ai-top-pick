"""면접 질문·응시 조회와 저장 (코드베이스 1. main-api 5장 InterviewRepo)."""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import SessionStatus, ValidStatus
from app.models.interview import InterviewQuestion, InterviewSession
from app.models.posting import CompanyQuestion


class InterviewRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_valid_questions(self, application_id: int) -> list[tuple[InterviewQuestion, str | None]]:
        """유효 질문을 순번대로. 기업 질문은 내용이 company_question에 있어 함께 돌려준다 (테이블 명세서)."""
        rows = await self.db.execute(
            select(InterviewQuestion, CompanyQuestion.content)
            .outerjoin(CompanyQuestion, CompanyQuestion.company_question_id == InterviewQuestion.company_question_id)
            .where(
                InterviewQuestion.application_id == application_id,
                InterviewQuestion.question_status == ValidStatus.VALID.value,
            )
            .order_by(InterviewQuestion.seq, InterviewQuestion.question_id)
        )
        return [(q, company) for q, company in rows]

    async def get_session_by_application(self, application_id: int) -> InterviewSession | None:
        """interview_session.application_id는 UNIQUE다. 지원서당 응시는 하나다."""
        return await self.db.scalar(select(InterviewSession).where(InterviewSession.application_id == application_id))

    async def create_session(self, application_id: int, camera_ok: bool, mic_ok: bool, now: datetime) -> InterviewSession:
        session = InterviewSession(
            application_id=application_id, camera_checked=camera_ok, mic_checked=mic_ok,
            started_at=now, status=SessionStatus.IN_PROGRESS.value, attempt_no=1,
        )
        self.db.add(session)
        await self.db.flush()
        return session

    async def mark_revealed(self, question_id: int) -> None:
        await self.db.execute(
            update(InterviewQuestion).where(InterviewQuestion.question_id == question_id).values(is_revealed=True)
        )
