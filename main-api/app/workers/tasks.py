from app.services import embedding_batch
from app.services.progress_batch import advance_posting_progress
from app.workers.celery_app import celery_app


@celery_app.task(name="posting.advance_progress")
def advance_progress() -> dict[str, int]:
    """전형 일정이 지난 공고의 진행 상태를 올린다 (celery-beat가 1분마다 실행)."""
    return advance_posting_progress()


@celery_app.task(name="embedding.embed_company_documents")
def embed_company_documents(job_id: int) -> int:
    """공고의 프로젝트 문서를 청크로 나눠 임베딩한다 (공고 등록, 등록된 공고의 문서 변경 때 main-api가 보낸다)."""
    return embedding_batch.embed_company_documents(job_id)
