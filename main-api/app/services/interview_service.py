"""AI 화상 면접 응시 (코드베이스 1. main-api 6.6 InterviewService).

실시간 면접 1단계: 안내(22), 응시 입구(23), 그래프 시작 요청 본문, 질문 공개 표시, 응시 완료.
2단계: 답변 영상 저장(save_answer_video), 답변·STT 저장(persist_answer).
점수 저장은 3단계, 표정 재처리는 3단계, 중단(suspend_session)은 5단계에서 넣는다.
"""

from datetime import datetime, timezone

from fastapi import UploadFile
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.domain.enums import JobStatus, JobType, SessionStatus, StageResult, StageType, ValidStatus
from app.domain.rules import is_interview_open
from app.models.application import Application, ApplicationStage
from app.models.batch import BatchJob
from app.models.interview import InterviewAnswer, InterviewQuestion, InterviewSession, SttRecord
from app.models.member import Member
from app.models.posting import EvalCriteria, JobPosting, PostingEvalRatio
from app.realtime import upload_registry
from app.repositories.interview_repo import InterviewRepo
from app.schemas.interview import InterviewGuide, SessionOut, VideoOut
from app.services import file_service
from app.workers.payloads import applicant_documents, posting_brief


def _not_available(message: str) -> AppError:
    return AppError(409, ErrorCode.INTERVIEW_NOT_AVAILABLE, message)


class InterviewService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = InterviewRepo(db)

    async def _own(self, member: Member, application_id: int) -> tuple[Application, JobPosting]:
        """본인 지원서만. 남의 지원서는 있어도 없는 것처럼 404."""
        row = (
            await self.db.execute(
                select(Application, JobPosting)
                .join(JobPosting, JobPosting.posting_id == Application.posting_id)
                .where(Application.application_id == application_id, Application.applicant_id == member.member_id)
            )
        ).first()
        if row is None:
            raise AppError(404, ErrorCode.APPLICATION_NOT_FOUND, "지원서를 찾을 수 없습니다.")
        return row[0], row[1]

    async def _doc_passed(self, application_id: int) -> bool:
        result = await self.db.scalar(
            select(ApplicationStage.result).where(
                ApplicationStage.application_id == application_id,
                ApplicationStage.stage_type == StageType.DOCUMENT.value,
            )
        )
        return result == StageResult.PASS.value

    async def _questions_ready(self, application_id: int) -> bool:
        """'면접 질문 생성' 작업이 끝났는지 (코드베이스 6.6 enter_session 3번)."""
        status = await self.db.scalar(
            select(BatchJob.status).where(
                BatchJob.job_type == JobType.INTERVIEW_QUESTIONS.value, BatchJob.application_id == application_id
            )
        )
        return status == JobStatus.DONE.value

    async def get_guide(self, member: Member, application_id: int, now: datetime | None = None) -> InterviewGuide:
        """APP-014, APP-018 화면 22. 면접 마감이 지났으면 기술적 테스트(23)로 넘어가지 않게 can_enter를 거짓으로 준다."""
        now = now or datetime.now(timezone.utc)
        application, posting = await self._own(member, application_id)
        reason = await self._enter_problem(application, posting, now)
        return InterviewGuide(
            application_id=application_id,
            position_name=posting.position_name,
            question_count=len(await self.repo.list_valid_questions(application_id)),
            think_time_sec=posting.think_time_sec or 0,
            answer_time_sec=posting.answer_time_sec or 0,
            interview_start_at=posting.interview_start_at,
            interview_end_at=posting.interview_end_at,
            interview_result_at=posting.interview_result_at,
            can_enter=reason is None,
            reason=reason,
        )

    async def _enter_problem(self, application: Application, posting: JobPosting, now: datetime) -> str | None:
        """응시 입구 검사 1~3번과 5번(완료·중단). 문제가 없으면 None."""
        if not await self._doc_passed(application.application_id):
            return "서류 전형 합격자만 면접에 응시할 수 있습니다."
        if not is_interview_open(posting, now):
            return "면접 기간이 아닙니다."
        if not await self._questions_ready(application.application_id):
            return "면접 질문을 준비하고 있습니다. 잠시 후 다시 시도해 주세요."
        session = await self.repo.get_session_by_application(application.application_id)
        if session and session.status == SessionStatus.COMPLETED.value:
            return "이미 면접을 마쳤습니다."
        if session and session.status == SessionStatus.ABORTED.value:
            # 문의 처리 상태에 따른 재시험은 실시간 면접 5단계(문의·예외 처리)에서 넣는다
            return "중단된 면접입니다. 처리 결과를 기다려 주세요."
        return None

    async def enter_session(
        self, member: Member, application_id: int, camera_ok: bool, mic_ok: bool, now: datetime | None = None
    ) -> SessionOut:
        """APP-015 응시 입구. 처음에만 응시를 만들고, 그 뒤로는 같은 응시를 돌려준다 (재접속).
        검사 순서: 서류 합격 → 면접 기간 → 질문 생성 완료 → 카메라·마이크 → 기존 응시 (코드베이스 6.6)."""
        now = now or datetime.now(timezone.utc)
        application, posting = await self._own(member, application_id)
        if (problem := await self._enter_problem(application, posting, now)) is not None:
            raise _not_available(problem)
        if not (camera_ok and mic_ok):
            raise _not_available("카메라와 마이크를 모두 확인해야 면접을 시작할 수 있습니다.")
        session = await self.repo.get_session_by_application(application_id)
        resumed = session is not None
        if session is None:
            session = await self.repo.create_session(application_id, camera_ok, mic_ok, now)
        await self.db.commit()
        return SessionOut(session_id=session.session_id, status=session.status, resumed=resumed)

    async def get_own_session(self, member: Member, session_id: int) -> InterviewSession | None:
        """WebSocket이 쓴다. 본인 응시이고 '진행 중'일 때만."""
        return await self.db.scalar(
            select(InterviewSession)
            .join(Application, Application.application_id == InterviewSession.application_id)
            .where(
                InterviewSession.session_id == session_id,
                Application.applicant_id == member.member_id,
                InterviewSession.status == SessionStatus.IN_PROGRESS.value,
            )
        )

    async def build_start_payload(self, session: InterviewSession) -> dict:
        """StartInterviewRequest (규약 2.2). 질문 목록은 처음 시작할 때만 그래프 State로 쓰인다.
        이미 질문을 공개했으면(재접속) resume을 참으로 보낸다. 체크포인트가 진행 상태를 가진다."""
        application = await self.db.get(Application, session.application_id)
        posting = await self.db.get(JobPosting, application.posting_id)
        ratios = {
            name: ratio
            for name, ratio in await self.db.execute(
                select(EvalCriteria.criteria_name, PostingEvalRatio.ratio)
                .join(PostingEvalRatio, PostingEvalRatio.criteria_id == EvalCriteria.criteria_id)
                .where(PostingEvalRatio.posting_id == posting.posting_id, EvalCriteria.stage_type == StageType.INTERVIEW.value)
            )
        }
        rows = await self.repo.list_valid_questions(application.application_id)
        questions = [
            {
                "qkey": f"q{q.question_id}",
                "question_id": q.question_id,
                "kind": "기업" if q.company_question_id else ("꼬리" if q.parent_question_id else "AI"),
                "question_type": q.question_type,
                "parent_qkey": f"q{q.parent_question_id}" if q.parent_question_id else None,
                "text": q.content or company or "",
            }
            for q, company in rows
        ]
        # 지원자 서류는 AI 직무 질문을 대체할 때 쓴다 (5단계). worker와 같은 함수로 만든다.
        # 포트폴리오 파일이 없어도 면접은 시작한다
        documents = await self.db.run_sync(
            lambda s: applicant_documents(s, s.get(Application, application.application_id), missing_portfolio_ok=True)
        )
        return {
            "session_id": session.session_id,
            "posting_id": posting.posting_id,
            "resume": any(q.is_revealed for q, _ in rows),
            "settings": {
                "follow_up_enabled": bool(posting.follow_up_enabled),
                "think_time_sec": posting.think_time_sec or 0,
                "answer_time_sec": posting.answer_time_sec or 0,
                "ratios": ratios,
            },
            "questions": questions,
            "posting": posting_brief(posting),
            "documents": documents,
        }

    async def mark_presented(self, question_id: int) -> None:
        """SYS-011 질문을 제시하면 is_revealed를 참으로 바꾼다."""
        await self.repo.mark_revealed(question_id)
        await self.db.commit()

    async def finish_session(self, session_id: int, now: datetime | None = None) -> None:
        """워크플로우 5-8 응시 '완료', 종료 일시 기록.
        '면접 보고서' 작업 등록(아키텍처 8)은 면접 보고서를 만드는 실시간 면접 6단계에서 넣는다."""
        session = await self.db.get(InterviewSession, session_id)
        session.status = SessionStatus.COMPLETED.value
        session.ended_at = now or datetime.now(timezone.utc)
        await self.db.commit()

    async def save_answer_video(self, member: Member, session_id: int, question_id: int, upload: UploadFile) -> VideoOut:
        """APP-016 답변 영상(webm) 저장. 본인의 '진행 중' 응시와 그 지원서의 질문만 받는다.
        저장을 마치면 답변을 기다리는 WebSocket에 알린다 (UploadRegistry)."""
        session = await self.get_own_session(member, session_id)
        owns = session is not None and await self.db.scalar(
            select(InterviewQuestion.question_id).where(
                InterviewQuestion.question_id == question_id, InterviewQuestion.application_id == session.application_id
            )
        )
        if not owns:
            raise AppError(404, ErrorCode.INTERVIEW_NOT_FOUND, "응시 중인 질문을 찾을 수 없습니다.")
        if not (upload.content_type or "").startswith("video/webm"):
            raise AppError(422, ErrorCode.FILE_INVALID, "webm 영상만 올릴 수 있습니다.")
        limit = get_settings().MAX_VIDEO_MB * 1024 * 1024
        data = await upload.read(limit + 1)
        if len(data) > limit:
            raise AppError(413, ErrorCode.FILE_TOO_LARGE, f"영상은 {get_settings().MAX_VIDEO_MB}MB 이하여야 합니다.")
        path = f"interviews/{session_id}/{question_id}.webm"
        file_service.save(path, data)
        upload_registry.notify(session_id, question_id, path)
        return VideoOut(video_path=path)

    async def persist_answer(self, session_id: int, question_id: int, video_path: str | None, evaluation: dict) -> None:
        """답변과 구간별 STT를 저장한다 (워크플로우 5-6). 점수는 실시간 면접 3단계에서 채운다.
        같은 질문에 이미 저장한 답변이 있으면(저장 직후 끊겨 다시 답한 경우) 무효로 돌리고 새로 저장한다."""
        await self.db.execute(
            update(InterviewAnswer)
            .where(InterviewAnswer.session_id == session_id, InterviewAnswer.question_id == question_id,
                   InterviewAnswer.answer_status == ValidStatus.VALID.value)
            .values(answer_status=ValidStatus.INVALID.value)
        )
        answer = InterviewAnswer(
            session_id=session_id, question_id=question_id, video_path=video_path,
            duration_sec=evaluation["duration_sec"], filler_count=evaluation["filler_count"],
            silence_sec=evaluation["silence_sec"], response_delay_sec=evaluation["response_delay_sec"],
            answer_status=ValidStatus.VALID.value,
        )
        self.db.add(answer)
        await self.db.flush()
        self.db.add_all(
            SttRecord(answer_id=answer.answer_id, time_offset_sec=seg["time_offset_sec"],
                      raw_text=seg["raw_text"], corrected_text=seg["corrected_text"])
            for seg in evaluation["segments"]
        )
        await self.db.commit()
