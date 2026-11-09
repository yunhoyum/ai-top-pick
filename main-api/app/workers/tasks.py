from app.services.progress_batch import advance_posting_progress
from app.workers.celery_app import celery_app


@celery_app.task(name="posting.advance_progress")
def advance_progress() -> dict[str, int]:
    """전형 일정이 지난 공고의 진행 상태를 올린다 (celery-beat가 1분마다 실행)."""
    return advance_posting_progress()
