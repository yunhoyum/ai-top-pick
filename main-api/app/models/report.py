from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, in_check
from app.domain.enums import PointType, SourceType


class StageReport(Base):
    __tablename__ = "stage_report"

    report_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # 전형당 1개
    application_stage_id: Mapped[int] = mapped_column(
        ForeignKey("application_stage.application_stage_id"), unique=True
    )
    ai_summary: Mapped[str | None] = mapped_column(Text)
    # 면접 보고서만 값이 있다 (서류는 NULL)
    follow_up_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReportScore(Base):
    __tablename__ = "report_score"

    report_id: Mapped[int] = mapped_column(ForeignKey("stage_report.report_id"), primary_key=True)
    criteria_id: Mapped[int] = mapped_column(
        ForeignKey("eval_criteria.criteria_id"), primary_key=True
    )
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    evidence: Mapped[str] = mapped_column(Text)


class ReportFit(Base):
    __tablename__ = "report_fit"

    fit_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("stage_report.report_id"))
    talent_content: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)


class ReportPoint(Base):
    __tablename__ = "report_point"
    __table_args__ = (in_check("point_type", PointType),)

    point_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("stage_report.report_id"))
    criteria_id: Mapped[int | None] = mapped_column(ForeignKey("eval_criteria.criteria_id"))
    point_type: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)


class EvidenceSentence(Base):
    """보고서 항목 점수 또는 면접 답변 평가의 근거가 된 회사 문서 문장 사본."""

    __tablename__ = "evidence_sentence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["report_id", "criteria_id"],
            ["report_score.report_id", "report_score.criteria_id"],
            ondelete="CASCADE",
        ),
        # 한 행은 보고서 항목과 답변 중 정확히 한 곳에만 속한다
        CheckConstraint(
            "(report_id IS NOT NULL AND criteria_id IS NOT NULL AND answer_id IS NULL)"
            " OR (report_id IS NULL AND criteria_id IS NULL AND answer_id IS NOT NULL)",
            name="exactly_one_target",
        ),
        UniqueConstraint(
            "report_id", "criteria_id", "answer_id", "seq", postgresql_nulls_not_distinct=True
        ),
        in_check("source_type", SourceType),
    )

    evidence_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    report_id: Mapped[int | None] = mapped_column(BigInteger)
    criteria_id: Mapped[int | None] = mapped_column(Integer)
    answer_id: Mapped[int | None] = mapped_column(
        ForeignKey("interview_answer.answer_id", ondelete="CASCADE")
    )
    source_type: Mapped[str] = mapped_column(String(255))
    source_id: Mapped[int | None] = mapped_column(BigInteger)
    # 재임베딩으로 바뀔 수 있어 FK를 걸지 않는다
    chunk_id: Mapped[int | None] = mapped_column(BigInteger)
    seq: Mapped[int] = mapped_column(Integer)
    sentence: Mapped[str] = mapped_column(Text)
