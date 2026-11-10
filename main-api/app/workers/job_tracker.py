"""worker에서 batch_job 상태를 바꾼다 (Celery 3장).

실행마다 시작 일시를 열쇠로 쓴다. 실행 중에 같은 작업이 다시 요청되면(job_queue.request) 행이 '대기'로 돌아가고
시작 일시가 지워진다. 그러면 먼저 돌던 실행은 끝나도 상태를 바꾸지 못하고, 새 실행의 결과만 남는다.
"""

from datetime import datetime

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.domain.enums import JobStatus
from app.models.batch import BatchJob


def start(db: Session, job_id: int) -> datetime | None:
    """'대기'일 때만 '실행 중'으로 바꾸고 시작 일시를 돌려준다. 이미 실행 중이거나 끝났으면 None."""
    return db.execute(
        update(BatchJob)
        .where(BatchJob.job_id == job_id, BatchJob.status == JobStatus.PENDING.value)
        .values(status=JobStatus.RUNNING.value, started_at=func.clock_timestamp(), error_message=None)
        .returning(BatchJob.started_at)
    ).scalar_one_or_none()


def done(db: Session, job_id: int, started_at: datetime) -> bool:
    """'완료'로 바꾼다. 이 실행이 더 이상 현재 실행이 아니면(다시 요청됨) 바꾸지 않고 거짓."""
    result = db.execute(
        _this_run(job_id, started_at).values(status=JobStatus.DONE.value, finished_at=func.clock_timestamp())
    )
    return result.rowcount == 1


def fail(db: Session, job_id: int, started_at: datetime, error: str) -> None:
    db.execute(
        _this_run(job_id, started_at).values(
            status=JobStatus.FAILED.value,
            error_message=error,
            retry_count=BatchJob.retry_count + 1,
            finished_at=func.clock_timestamp(),
        )
    )


def _this_run(job_id: int, started_at: datetime):
    return update(BatchJob).where(
        BatchJob.job_id == job_id,
        BatchJob.status == JobStatus.RUNNING.value,
        BatchJob.started_at == started_at,
    )
