"""main-api에서 배치 작업을 등록하고 Celery로 보낸다 (Celery 3장 JobTracker의 register·requeue·enqueue)."""

import logging

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import JobStatus, JobType
from app.models.batch import BatchJob

log = logging.getLogger(__name__)

# 작업 종류 → Celery 작업 이름 (workers/tasks.py)
TASK_NAMES = {
    JobType.COMPANY_DOC_EMBED.value: "embedding.embed_company_documents",
    JobType.DOC_REPORT.value: "report.generate_document_report",
}


async def request(db: AsyncSession, job_type: str, posting_id: int, application_id: int | None = None) -> int:
    """작업 행을 '대기'로 만든다. 행이 없으면 넣고, 있으면 '대기'로 되돌린다. commit은 부르는 쪽이 한다.
    실행 중인 행을 되돌리면 그 실행은 끝나도 상태를 바꾸지 않는다 (시작 일시가 달라져서). 새로 보낸 작업이 다시 돈다."""
    stmt = (
        insert(BatchJob)
        .values(job_type=job_type, posting_id=posting_id, application_id=application_id)
        .on_conflict_do_update(
            constraint="uq_batch_job_job_type",
            set_={"status": JobStatus.PENDING.value, "error_message": None, "started_at": None, "finished_at": None},
        )
        .returning(BatchJob.job_id)
    )
    return (await db.execute(stmt)).scalar_one()


def send(job_type: str, job_id: int) -> None:
    """commit한 뒤에 부른다. 보내지 못해도 요청은 실패시키지 않는다. 행은 '대기'로 남는다."""
    from app.workers.celery_app import celery_app

    try:
        celery_app.send_task(TASK_NAMES[job_type], args=[job_id])
    except Exception:
        log.exception("작업 %s(%s)을 보내지 못했습니다. batch_job은 '대기'로 남습니다", job_id, job_type)
