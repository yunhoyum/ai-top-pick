from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ApplicationWriteStatus, HandlingStatus, SessionStatus, StageResult, StageType
from app.domain.rules import is_accepting_applications
from app.models.application import Application, ApplicationStage
from app.models.interview import InterviewSession
from app.models.member import Member
from app.models.posting import JobPosting
from app.repositories.inquiry_repo import InquiryRepo
from app.schemas.application_status import ApplicationStatusItem

STATUS_DRAFT = "작성 중"
STATUS_DOC_PENDING = "서류 전형 진행 중"
STATUS_INTERVIEW_UPCOMING = "면접 전형 예정"
STATUS_INTERVIEW_ONGOING = "면접 전형 진행 중"
# 면접이 문의 처리로 중단됐을 때 (APP-018, 화면 21-2·21-3). 관리자 대기면 처리 중, 그 밖에는 재접속 가능
STATUS_INTERVIEW_HOLD = "처리 중"
STATUS_INTERVIEW_RECONNECT = "재접속 가능"
STATUS_INTERVIEW_WAITING = "면접 결과 대기"
STATUS_DONE = "면접 전형 완료"
STATUS_ENDED = "전형 종료"


def _shown_result(result: str | None, announce_at: datetime | None, now: datetime) -> str | None:
    """합격자 발표 일시가 되기 전에는 결과를 알려 주지 않는다. 필수 기술 미달은 불합격으로 보여 준다."""
    if result is None or announce_at is None or now < announce_at:
        return None
    return "합격" if result == StageResult.PASS.value else "불합격"


class ApplicationStatusService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_mine(self, member: Member, now: datetime | None = None) -> list[ApplicationStatusItem]:
        """APP-012, APP-017 내 지원 목록과 전형 결과. 최근에 만든 지원서가 먼저 나온다."""
        now = now or datetime.now(timezone.utc)
        rows = (
            await self.db.execute(
                select(Application, JobPosting)
                .join(JobPosting, JobPosting.posting_id == Application.posting_id)
                .where(Application.applicant_id == member.member_id)
                .order_by(Application.application_id.desc())
            )
        ).all()
        ids = [a.application_id for a, _ in rows]
        stages = {
            (s.application_id, s.stage_type): s.result
            for s in await self.db.scalars(select(ApplicationStage).where(ApplicationStage.application_id.in_(ids)))
        }
        taken = set(
            await self.db.scalars(
                select(InterviewSession.application_id).where(
                    InterviewSession.application_id.in_(ids), InterviewSession.status == SessionStatus.COMPLETED.value
                )
            )
        )
        # 중단된 응시: 지원서 → 관리자 대기인지 (마지막 미해결 문의의 처리 상태, 코드베이스 6.4)
        suspended = {}
        for s in await self.db.scalars(select(InterviewSession).where(
            InterviewSession.application_id.in_(ids), InterviewSession.status == SessionStatus.ABORTED.value
        )):
            last = await InquiryRepo(self.db).get_last_unresolved(s.session_id)
            suspended[s.application_id] = last is not None and last.handling_status == HandlingStatus.ADMIN_WAITING.value

        items = []
        for application, posting in rows:
            if application.write_status == ApplicationWriteStatus.DRAFT.value:
                # 작성 중인 지원서는 접수 기간일 때만 보여 준다 (접수가 끝나면 전형에 들어가지 않는다)
                if not is_accepting_applications(posting, now):
                    continue
                doc_result = interview_result = None
            else:
                doc_result = _shown_result(
                    stages.get((application.application_id, StageType.DOCUMENT.value)), posting.doc_result_at, now
                )
                interview_result = (
                    _shown_result(
                        stages.get((application.application_id, StageType.INTERVIEW.value)), posting.interview_result_at, now
                    )
                    if doc_result == "합격"
                    else None
                )
            items.append(
                ApplicationStatusItem(
                    application_id=application.application_id,
                    posting_id=posting.posting_id,
                    position_name=posting.position_name,
                    write_status=application.write_status,
                    submitted_at=application.submitted_at,
                    status=self._interview_hold(
                        self._status(application, posting, doc_result, interview_result, now),
                        suspended.get(application.application_id),
                    ),
                    doc_end_at=posting.doc_end_at,
                    doc_result_at=posting.doc_result_at,
                    interview_start_at=posting.interview_start_at,
                    interview_end_at=posting.interview_end_at,
                    interview_result_at=posting.interview_result_at,
                    doc_result=doc_result,
                    interview_result=interview_result,
                    interview_taken=application.application_id in taken,
                    can_view_interview_guide=doc_result == "합격"
                    and posting.interview_end_at is not None
                    and now < posting.interview_end_at
                    # 관리자 처리 전에는 응시 버튼을 막는다 (APP-018)
                    and suspended.get(application.application_id) is not True,
                )
            )
        return items

    @staticmethod
    def _interview_hold(status: str, waiting_admin: bool | None) -> str:
        """면접 기간 중 중단된 응시면 처리 중(관리자 대기) 또는 재접속 가능. 마감이 지나면 원래 상태다."""
        if waiting_admin is None or status != STATUS_INTERVIEW_ONGOING:
            return status
        return STATUS_INTERVIEW_HOLD if waiting_admin else STATUS_INTERVIEW_RECONNECT

    @staticmethod
    def _status(
        application: Application, posting: JobPosting, doc_result: str | None, interview_result: str | None, now: datetime
    ) -> str:
        if application.write_status == ApplicationWriteStatus.DRAFT.value:
            return STATUS_DRAFT
        if doc_result is None:
            return STATUS_DOC_PENDING
        if doc_result == "불합격":
            return STATUS_ENDED
        if interview_result is not None:
            return STATUS_DONE if interview_result == "합격" else STATUS_ENDED
        if posting.interview_end_at and now >= posting.interview_end_at:
            return STATUS_INTERVIEW_WAITING
        if posting.interview_start_at and now >= posting.interview_start_at:
            return STATUS_INTERVIEW_ONGOING
        return STATUS_INTERVIEW_UPCOMING
