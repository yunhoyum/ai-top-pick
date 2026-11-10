"""doc_chunk 읽기 모델. 테이블은 main-api 마이그레이션이 만든다. ai-service는 읽기만 한다."""

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIM = 1024


class Base(DeclarativeBase):
    pass


class DocChunk(Base):
    __tablename__ = "doc_chunk"

    chunk_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    posting_id: Mapped[int] = mapped_column(BigInteger)
    source_type: Mapped[str] = mapped_column(String(255))
    source_id: Mapped[int] = mapped_column(BigInteger)
    seq: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector(EMBEDDING_DIM))
