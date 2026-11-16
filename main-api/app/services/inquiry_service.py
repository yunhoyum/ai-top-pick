"""면접 중 기술 문의 (코드베이스 1. main-api 6.7 InquiryService, SYS-003·012, APP-013, ADM-026·041).

면접 WebSocket이 문의를 열고(open) 대화를 저장하고(add_message) 판단을 기록한다(close).
처리 상태: 해결 → 'AI 처리' / 미해결·지원자 측 → 'AI 미처리' / 미해결·시스템 측·원인 판단 불가 → '관리자 대기'.
관리자가 '재개'하면 '관리자 처리 완료'와 처리 시각을 남긴다. 지원자에게는 내 지원 현황의 '재접속 가능'으로 알린다
(SYS-012, 메일 등 별도 알림은 두지 않음, 2026-11-16 결정). ai-service는 부르지 않는다. 그래프는 재접속 때 깨어난다.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ErrorCode
from app.domain.enums import DefectCause, HandlingStatus
from app.models.inquiry import Inquiry, JudgmentType
from app.models.interview import InterviewQuestion
from app.models.member import Member
from app.models.posting import CompanyQuestion
from app.repositories.inquiry_repo import InquiryRepo
from app.schemas.inquiry import ChatLine, InquiryDetail, InquiryItem, LogLineOut


def handling_status(resolved: bool, cause: str) -> str:
    if resolved:
        return HandlingStatus.AI_HANDLED.value
    return HandlingStatus.AI_UNHANDLED.value if cause == DefectCause.APPLICANT.value else HandlingStatus.ADMIN_WAITING.value


class InquiryService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = InquiryRepo(db)

    # ---------- 면접 중 (WebSocket) ----------
    async def open(self, session_id: int, question_id: int | None, logs: list[dict]) -> int:
        """문의 시작 시각을 기록하고 직전 세션 이벤트를 system_log로 옮긴다 (워크플로우 6-1)."""
        inquiry = await self.repo.create(session_id, question_id)
        await self.repo.add_logs(inquiry.inquiry_id, logs)
        await self.db.commit()
        return inquiry.inquiry_id

    async def add_message(self, inquiry_id: int, speaker: str, content: str) -> None:
        await self.repo.add_message(inquiry_id, speaker, content)
        await self.db.commit()

    async def add_logs(self, inquiry_id: int, logs: list[dict]) -> None:
        await self.repo.add_logs(inquiry_id, logs)
        await self.db.commit()

    async def close(self, inquiry_id: int, judgment: dict) -> tuple[str, str | None]:
        """(해결 여부, 원인)으로 판단 결과 코드를 찾아 저장한다 (SYS-003). (처리 상태, 후속 조치)를 돌려준다."""
        kind = await self.repo.get_judgment_type(judgment["resolved"], judgment["cause"])
        inquiry = await self.db.get(Inquiry, inquiry_id)
        inquiry.judgment_code = kind.judgment_code
        inquiry.ended_at = datetime.now(timezone.utc)
        inquiry.judgment_basis = judgment["judgment_basis"]
        inquiry.ai_action = judgment["ai_action"]
        inquiry.handling_detail = judgment["handling_detail"]
        inquiry.ai_attempt_count = judgment["ai_attempt_count"]
        inquiry.handling_status = handling_status(judgment["resolved"], judgment["cause"])
        await self.db.commit()
        return inquiry.handling_status, kind.follow_up

    # ---------- 관리자 (화면 26) ----------
    async def list_inquiries(self, admin: Member, status: str | None, posting_id: int | None) -> list[InquiryItem]:
        """ADM-026 본인 공고의 문의. 처리 상태 4개 탭으로 거른다. 판단이 끝난 문의만 보인다."""
        rows = await self.repo.list_for_admin(admin.member_id, status, posting_id)
        return [await self._item(*row) for row in rows]

    async def get_inquiry(self, admin: Member, inquiry_id: int) -> InquiryDetail:
        """ADM-026 상세: 문의 정보, 챗봇 대화, 시스템 로그, 처리 결과."""
        inquiry, application, posting = await self._owned(admin, inquiry_id)
        item = await self._item(inquiry, application, posting)
        kind = await self.db.get(JudgmentType, inquiry.judgment_code) if inquiry.judgment_code else None
        return InquiryDetail(
            **item.model_dump(),
            judgment_basis=inquiry.judgment_basis, ai_action=inquiry.ai_action, handling_detail=inquiry.handling_detail,
            follow_up=kind.follow_up if kind else None, handled_at=inquiry.handled_at,
            messages=[ChatLine(speaker=m.speaker, content=m.content) for m in await self.repo.messages(inquiry_id)],
            logs=[LogLineOut(logged_at=l.logged_at, content=l.content) for l in await self.repo.logs(inquiry_id)],
        )

    async def resume_by_admin(self, admin: Member, inquiry_id: int, now: datetime | None = None) -> InquiryDetail:
        """ADM-041 '관리자 대기' 문의를 처리 완료로 바꾼다. 지원자는 내 지원 현황에서 '재접속 가능'을 본다 (SYS-012).
        면접 마감이 지나면 재개해도 재시험은 볼 수 없다 (응시 입구가 막는다)."""
        inquiry, _, _ = await self._owned(admin, inquiry_id)
        if inquiry.handling_status != HandlingStatus.ADMIN_WAITING.value:
            raise AppError(409, ErrorCode.INQUIRY_NOT_WAITING, "관리자 대기 중인 문의만 재개할 수 있습니다.")
        inquiry.handling_status = HandlingStatus.ADMIN_DONE.value
        inquiry.handled_at = now or datetime.now(timezone.utc)
        await self.db.commit()
        return await self.get_inquiry(admin, inquiry_id)

    async def _owned(self, admin: Member, inquiry_id: int):
        row = await self.repo.get_owned(admin.member_id, inquiry_id)
        if row is None:
            raise AppError(404, ErrorCode.INQUIRY_NOT_FOUND, "문의를 찾을 수 없습니다.")
        return row

    async def _item(self, inquiry: Inquiry, application, posting) -> InquiryItem:
        applicant = await self.db.get(Member, application.applicant_id)
        question_text = None
        if inquiry.question_id:
            q = await self.db.get(InterviewQuestion, inquiry.question_id)
            question_text = q.content or (await self.db.scalar(
                select(CompanyQuestion.content).where(CompanyQuestion.company_question_id == q.company_question_id)
            ) if q.company_question_id else None)
        kind = await self.db.get(JudgmentType, inquiry.judgment_code) if inquiry.judgment_code else None
        return InquiryItem(
            inquiry_id=inquiry.inquiry_id, posting_id=posting.posting_id, position_name=posting.position_name,
            application_id=application.application_id, applicant_name=applicant.name if applicant else None,
            question_text=question_text, started_at=inquiry.started_at, ended_at=inquiry.ended_at,
            handling_status=inquiry.handling_status, cause=kind.cause if kind else None,
            ai_attempt_count=inquiry.ai_attempt_count,
        )
