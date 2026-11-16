"""면접 보고서 작업 (Celery 4장 generate_interview_report, 아키텍처 8·9.4).

응시 '완료' → main-api가 '면접 보고서' 작업 등록(InterviewService.finish_session) → 지원자 1명씩 ai-service 호출 → 결과 저장.
보고서 점수는 실시간 답변별 점수의 평균이다. 면접이 끝난 뒤 다시 채점하지 않는다 (루브릭 설계서 8.2).
미응시자는 보고서가 없고 0점으로 본다 (루브릭 설계서 9).
"""

import logging

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.clients.ai_service import AiServiceClient
from app.domain.enums import StageType, ValidStatus
from app.models.batch import BatchJob
from app.models.interview import InterviewQuestion
from app.services.document_report_batch import _save
from app.services.progress_batch import get_engine
from app.workers import job_tracker
from app.workers.payloads import build_interview_report_payload

log = logging.getLogger(__name__)


def generate_interview_report(
    job_id: int, engine: Engine | None = None, client: AiServiceClient | None = None
) -> int | None:
    """지원자 1명의 면접 보고서를 만들어 저장한다. report_id를 돌려준다. 작업이 '대기'가 아니면 None."""
    client = client or AiServiceClient()
    with Session(engine or get_engine()) as db:
        started_at = job_tracker.start(db, job_id)
        db.commit()
        if started_at is None:
            log.info("작업 %s는 대기 상태가 아니라 건너뜁니다", job_id)
            return None
        application_id = db.get(BatchJob, job_id).application_id

        try:
            result = client.create_interview_report(build_interview_report_payload(db, application_id))
            if not job_tracker.done(db, job_id, started_at):
                db.rollback()
                log.info("작업 %s가 실행 중에 다시 요청돼 결과를 쓰지 않습니다", job_id)
                return None
            report_id = _save(db, application_id, result, StageType.INTERVIEW.value, follow_up_count(db, application_id))
            db.commit()
        except Exception as e:
            db.rollback()
            job_tracker.fail(db, job_id, started_at, f"{type(e).__name__}: {e}")
            db.commit()
            raise
    log.info("지원서 %s 면접 보고서 %s를 저장했습니다", application_id, report_id)
    return report_id


def follow_up_count(db: Session, application_id: int) -> int:
    """유효 꼬리질문 수. 총점에 더하지 않는다 (SYS-008, 루브릭 설계서 9). 무효 처리된 꼬리질문은 세지 않는다."""
    return db.scalar(
        select(func.count()).select_from(InterviewQuestion).where(
            InterviewQuestion.application_id == application_id,
            InterviewQuestion.parent_question_id.is_not(None),
            InterviewQuestion.question_status == ValidStatus.VALID.value,
        )
    )
