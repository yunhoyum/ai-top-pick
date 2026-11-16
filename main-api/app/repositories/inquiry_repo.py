"""문의·챗봇 대화·시스템 로그 조회와 저장 (코드베이스 1. main-api 5장 InquiryRepo)."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import HandlingStatus
from app.models.application import Application
from app.models.inquiry import ChatMessage, Inquiry, JudgmentType, SystemLog
from app.models.interview import InterviewSession
from app.models.posting import JobPosting


class InquiryRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, session_id: int, question_id: int | None) -> Inquiry:
        inquiry = Inquiry(session_id=session_id, question_id=question_id)
        self.db.add(inquiry)
        await self.db.flush()
        return inquiry

    async def add_message(self, inquiry_id: int, speaker: str, content: str) -> None:
        seq = await self.db.scalar(select(func.count()).where(ChatMessage.inquiry_id == inquiry_id))
        self.db.add(ChatMessage(inquiry_id=inquiry_id, seq=seq + 1, speaker=speaker, content=content))

    async def add_logs(self, inquiry_id: int, logs: list[dict]) -> None:
        self.db.add_all(
            SystemLog(inquiry_id=inquiry_id, logged_at=datetime.fromisoformat(l["logged_at"]), content=l["content"])
            for l in logs
        )

    async def get_judgment_type(self, resolved: bool, cause: str) -> JudgmentType:
        return await self.db.scalar(
            select(JudgmentType).where(JudgmentType.ai_handled.is_(resolved), JudgmentType.cause == cause)
        )

    async def get_last_unresolved(self, session_id: int) -> Inquiry | None:
        """그 응시의 마지막 미해결 문의 (응시 중단의 원인). 처리 상태로 재접속을 정한다 (코드베이스 6.6)."""
        return await self.db.scalar(
            select(Inquiry)
            .where(Inquiry.session_id == session_id,
                   Inquiry.handling_status.in_([HandlingStatus.AI_UNHANDLED.value, HandlingStatus.ADMIN_WAITING.value,
                                                HandlingStatus.ADMIN_DONE.value]))
            .order_by(Inquiry.inquiry_id.desc())
            .limit(1)
        )

    async def list_for_admin(self, admin_id: int, handling_status: str | None, posting_id: int | None):
        """본인 공고의 문의 (ADM-026). (문의, 지원서, 공고) 목록. 최근 문의부터."""
        stmt = (
            select(Inquiry, Application, JobPosting)
            .join(InterviewSession, InterviewSession.session_id == Inquiry.session_id)
            .join(Application, Application.application_id == InterviewSession.application_id)
            .join(JobPosting, JobPosting.posting_id == Application.posting_id)
            .where(JobPosting.admin_id == admin_id, Inquiry.handling_status.is_not(None))
            .order_by(Inquiry.inquiry_id.desc())
        )
        if handling_status:
            stmt = stmt.where(Inquiry.handling_status == handling_status)
        if posting_id:
            stmt = stmt.where(JobPosting.posting_id == posting_id)
        return (await self.db.execute(stmt)).all()

    async def get_owned(self, admin_id: int, inquiry_id: int):
        """본인 공고의 문의 하나 (문의, 지원서, 공고). 남의 공고면 None."""
        return (
            await self.db.execute(
                select(Inquiry, Application, JobPosting)
                .join(InterviewSession, InterviewSession.session_id == Inquiry.session_id)
                .join(Application, Application.application_id == InterviewSession.application_id)
                .join(JobPosting, JobPosting.posting_id == Application.posting_id)
                .where(Inquiry.inquiry_id == inquiry_id, JobPosting.admin_id == admin_id)
            )
        ).first()

    async def messages(self, inquiry_id: int) -> list[ChatMessage]:
        return list(await self.db.scalars(
            select(ChatMessage).where(ChatMessage.inquiry_id == inquiry_id).order_by(ChatMessage.seq)
        ))

    async def logs(self, inquiry_id: int) -> list[SystemLog]:
        return list(await self.db.scalars(
            select(SystemLog).where(SystemLog.inquiry_id == inquiry_id).order_by(SystemLog.logged_at, SystemLog.log_id)
        ))
