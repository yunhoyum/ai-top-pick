"""회사 문서 임베딩 작업 (Celery 4장 embed_company_documents, 벡터 DB 설계서 10.2).

① 공고의 프로젝트 문서 PDF 텍스트를 모은다 ② 청크로 나눈다 ③ embed-server로 임베딩한다
④ 한 트랜잭션 안에서 공고의 기존 청크를 지우고 새 청크를 넣는다. 실패하면 이전 청크가 그대로 남는다.
"""

import logging

from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from app.clients.embed import EmbedClient
from app.core.config import get_settings
from app.domain.enums import ChunkSourceType
from app.models.batch import BatchJob, DocChunk
from app.models.posting import PostingDocument
from app.services import file_service
from app.services.progress_batch import get_engine
from app.workers import job_tracker
from app.workers.chunking import split_by_offsets
from app.workers.pdf_text import extract_text

log = logging.getLogger(__name__)


def embed_company_documents(job_id: int, engine: Engine | None = None, client: EmbedClient | None = None) -> int:
    """저장한 청크 수를 돌려준다. 작업이 '대기'가 아니면(이미 실행 중이거나 끝남) 아무것도 하지 않고 0."""
    client = client or EmbedClient()
    with Session(engine or get_engine()) as db:
        started_at = job_tracker.start(db, job_id)
        db.commit()
        if started_at is None:
            log.info("작업 %s는 대기 상태가 아니라 건너뜁니다", job_id)
            return 0
        posting_id = db.get(BatchJob, job_id).posting_id

        try:
            pieces = _chunk_documents(db, posting_id, client)
            vectors = client.embed([content for _, _, content in pieces]) if pieces else []
            # 같은 공고의 임베딩이 동시에 돌면 지우기·넣기가 섞인다. 공고 단위로 한 번에 하나만 쓰게 한다
            db.execute(select(func.pg_advisory_xact_lock(posting_id)))
            # 도는 동안 작업이 다시 요청됐으면 이 결과는 옛 문서 기준이다. 쓰지 않고 새 실행에 맡긴다
            if not job_tracker.done(db, job_id, started_at):
                db.rollback()
                log.info("작업 %s가 실행 중에 다시 요청돼 결과를 쓰지 않습니다", job_id)
                return 0
            db.execute(delete(DocChunk).where(DocChunk.posting_id == posting_id))
            db.add_all(
                DocChunk(
                    posting_id=posting_id,
                    source_type=ChunkSourceType.PROJECT_DOC.value,
                    source_id=document_id,
                    seq=seq,
                    content=content,
                    embedding=vector,
                )
                for (document_id, seq, content), vector in zip(pieces, vectors, strict=True)
            )
            db.commit()
        except Exception as e:
            db.rollback()
            job_tracker.fail(db, job_id, started_at, f"{type(e).__name__}: {e}")
            db.commit()
            raise
    log.info("공고 %s 회사 문서 청크 %d개를 저장했습니다", posting_id, len(pieces))
    return len(pieces)


def _chunk_documents(db: Session, posting_id: int, client: EmbedClient) -> list[tuple[int, int, str]]:
    """(문서 ID, 순번, 청크 텍스트) 목록. 순번은 문서 안에서 0부터 매긴다 (벡터 DB 설계서 4.3)."""
    settings = get_settings()
    documents = db.scalars(
        select(PostingDocument).where(PostingDocument.posting_id == posting_id).order_by(PostingDocument.document_id)
    ).all()
    pieces: list[tuple[int, int, str]] = []
    for document in documents:
        text = extract_text(file_service.resolve(document.file_path))
        if not text.strip():
            log.warning("문서 %s에서 텍스트를 찾지 못해 청크를 만들지 않습니다", document.document_id)
            continue
        offsets = client.tokenize([text])[0]
        chunks = split_by_offsets(text, offsets, settings.CHUNK_MAX_TOKENS, settings.CHUNK_OVERLAP_TOKENS)
        pieces += [(document.document_id, seq, chunk) for seq, chunk in enumerate(c for c in chunks if c)]
    return pieces
