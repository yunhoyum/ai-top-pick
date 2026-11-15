"""표정 분석 재처리 작업 (Celery 4장 reprocess_expressions, 아키텍처 8).

면접 중 ai-service의 표정 분석이 실패하면 main-api가 이 작업을 등록하고 끝나기를 기다린다.
지원자 1명 단위다. 그 지원자의 유효 답변 중 영상이 있고 주요 표정이 비어 있는 답변만 다시 분석한다.
worker가 vision-server를 직접 부른다. 둘 다 PC1에 있다 (아키텍처 2).
"""

import logging

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.clients.vision import VisionClient
from app.domain.enums import ValidStatus
from app.models.batch import BatchJob
from app.models.interview import InterviewAnswer, InterviewSession
from app.services.progress_batch import get_engine
from app.workers import job_tracker
from app.workers.expression import summarize_expression

log = logging.getLogger(__name__)


def reprocess_expressions(job_id: int, engine: Engine | None = None, client: VisionClient | None = None) -> int | None:
    """다시 분석해 표정을 채운 답변 수를 돌려준다. 작업이 '대기'가 아니면 None.
    답변 하나가 또 실패해도 나머지는 계속한다. 그 답변은 표정 없이 채점된다."""
    client = client or VisionClient()
    with Session(engine or get_engine()) as db:
        started_at = job_tracker.start(db, job_id)
        db.commit()
        if started_at is None:
            log.info("작업 %s는 대기 상태가 아니라 건너뜁니다", job_id)
            return None
        application_id = db.get(BatchJob, job_id).application_id
        answers = db.scalars(
            select(InterviewAnswer)
            .join(InterviewSession, InterviewSession.session_id == InterviewAnswer.session_id)
            .where(
                InterviewSession.application_id == application_id,
                InterviewAnswer.answer_status == ValidStatus.VALID.value,
                InterviewAnswer.video_path.is_not(None),
                InterviewAnswer.main_expression.is_(None),
            )
        ).all()
        filled = 0
        for answer in answers:
            try:
                main, ratio = summarize_expression(client.analyze(answer.video_path))
            except Exception as e:
                log.warning("답변 %s 표정 재분석 실패: %s", answer.answer_id, e)
                continue
            if main is not None:
                answer.main_expression, answer.expression_ratio = main, ratio
                filled += 1
        job_tracker.done(db, job_id, started_at)
        db.commit()
        return filled
