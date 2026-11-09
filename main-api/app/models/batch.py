from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, in_check
from app.domain.enums import ChunkSourceType, JobStatus, JobType

# KURE-v1 출력 차원
EMBEDDING_DIM = 1024


class BatchJob(Base):
    __tablename__ = "batch_job"
    __table_args__ = (
        # 같은 작업이 두 번 등록되지 않게 한다 (PostgreSQL 15 이상)
        UniqueConstraint(
            "job_type", "posting_id", "application_id", postgresql_nulls_not_distinct=True
        ),
        in_check("job_type", JobType),
        in_check("status", JobStatus),
    )

    job_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(255))
    posting_id: Mapped[int] = mapped_column(ForeignKey("job_posting.posting_id", ondelete="CASCADE"))
    # 지원자 단위 작업일 때만 값이 있다
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("application.application_id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(255), server_default=JobStatus.PENDING.value)
    retry_count: Mapped[int] = mapped_column(Integer, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocChunk(Base):
    """RAG 검색 대상인 회사 문서 청크. 벡터 인덱스(HNSW 등)는 두지 않는다."""

    __tablename__ = "doc_chunk"
    __table_args__ = (
        UniqueConstraint(
            "posting_id", "source_type", "source_id", "seq", postgresql_nulls_not_distinct=True
        ),
        Index("ix_doc_chunk_posting_id", "posting_id"),
        in_check("source_type", ChunkSourceType),
    )

    chunk_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    posting_id: Mapped[int] = mapped_column(ForeignKey("job_posting.posting_id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String(255))
    # 프로젝트 문서를 지우면 그 문서의 청크도 함께 지워진다
    source_id: Mapped[int] = mapped_column(
        ForeignKey("posting_document.document_id", ondelete="CASCADE")
    )
    seq: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
