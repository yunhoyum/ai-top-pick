"""면접 질문·응시 조회와 저장 (코드베이스 1. main-api 5장 InterviewRepo)."""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import SessionStatus, ValidStatus
from app.models.interview import InterviewAnswer, InterviewQuestion, InterviewSession, SttRecord
from app.models.posting import CompanyQuestion
from app.models.report import EvidenceSentence


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

    async def invalidate_answer(self, session_id: int, question_id: int) -> None:
        """그 질문의 유효 답변을 '무효'로 바꾼다."""
        await self.db.execute(
            update(InterviewAnswer)
            .where(InterviewAnswer.session_id == session_id, InterviewAnswer.question_id == question_id,
                   InterviewAnswer.answer_status == ValidStatus.VALID.value)
            .values(answer_status=ValidStatus.INVALID.value)
        )

    async def insert_answer(self, answer: InterviewAnswer) -> InterviewAnswer:
        self.db.add(answer)
        await self.db.flush()
        return answer

    async def insert_stt_records(self, answer_id: int, segments: list[dict]) -> None:
        self.db.add_all(
            SttRecord(answer_id=answer_id, time_offset_sec=seg["time_offset_sec"],
                      raw_text=seg["raw_text"], corrected_text=seg["corrected_text"])
            for seg in segments
        )

    async def insert_evidence(self, answer_id: int, evidence: list[dict]) -> None:
        """답변 내용 점수의 근거 문장 사본 (벡터 DB 설계서 8.4). 순번은 1부터."""
        self.db.add_all(
            EvidenceSentence(answer_id=answer_id, seq=i, source_type=e["source_type"], source_id=e.get("source_id"),
                             chunk_id=e.get("chunk_id"), sentence=e["sentence"])
            for i, e in enumerate(evidence, start=1)
        )

    async def get_valid_answer(self, session_id: int, question_id: int) -> InterviewAnswer | None:
        return await self.db.scalar(
            select(InterviewAnswer).where(
                InterviewAnswer.session_id == session_id, InterviewAnswer.question_id == question_id,
                InterviewAnswer.answer_status == ValidStatus.VALID.value,
            )
        )
