from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, in_check
from app.domain.enums import ApplicationWriteStatus, StageResult, StageType

# 지원서 하위 테이블은 지원서를 지우면 함께 지워진다 (제출 철회)
def _app_fk() -> ForeignKey:
    return ForeignKey("application.application_id", ondelete="CASCADE")


class Application(Base):
    __tablename__ = "application"
    __table_args__ = (
        UniqueConstraint("posting_id", "applicant_id"),
        in_check("write_status", ApplicationWriteStatus),
    )

    application_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    posting_id: Mapped[int] = mapped_column(ForeignKey("job_posting.posting_id"))
    applicant_id: Mapped[int] = mapped_column(ForeignKey("member.member_id"))
    # 지원 당시 인적사항
    applicant_name: Mapped[str | None] = mapped_column(String(255))
    applicant_phone: Mapped[str | None] = mapped_column(String(255))
    applicant_email: Mapped[str | None] = mapped_column(String(255))
    write_status: Mapped[str] = mapped_column(
        String(255), server_default=ApplicationWriteStatus.DRAFT.value
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Education(Base):
    __tablename__ = "education"

    education_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    application_id: Mapped[int] = mapped_column(_app_fk())
    school_name: Mapped[str | None] = mapped_column(String(255))
    major: Mapped[str | None] = mapped_column(String(255))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)


class Career(Base):
    __tablename__ = "career"

    career_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    application_id: Mapped[int] = mapped_column(_app_fk())
    company_name: Mapped[str | None] = mapped_column(String(255))
    job_role: Mapped[str | None] = mapped_column(String(255))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)


class ApplicantProject(Base):
    __tablename__ = "applicant_project"

    project_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    application_id: Mapped[int] = mapped_column(_app_fk())
    project_name: Mapped[str | None] = mapped_column(String(255))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)


class ApplicantSkill(Base):
    __tablename__ = "applicant_skill"
    __table_args__ = (CheckConstraint("self_score BETWEEN 1 AND 5", name="self_score_range"),)

    application_id: Mapped[int] = mapped_column(_app_fk(), primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skill.skill_id"), primary_key=True)
    self_score: Mapped[int | None] = mapped_column(Integer)


class SkillCase(Base):
    __tablename__ = "skill_case"

    skill_case_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    application_id: Mapped[int] = mapped_column(_app_fk())
    skill_id: Mapped[int | None] = mapped_column(ForeignKey("skill.skill_id"))
    seq: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str | None] = mapped_column(Text)


class EssayAnswer(Base):
    __tablename__ = "essay_answer"

    application_id: Mapped[int] = mapped_column(_app_fk(), primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("essay_topic.topic_id"), primary_key=True)
    content: Mapped[str | None] = mapped_column(Text)


class Portfolio(Base):
    __tablename__ = "portfolio"

    portfolio_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # 지원서당 1개
    application_id: Mapped[int] = mapped_column(_app_fk(), unique=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    file_path: Mapped[str] = mapped_column(String(255))


class ApplicationStage(Base):
    __tablename__ = "application_stage"
    __table_args__ = (
        UniqueConstraint("application_id", "stage_type"),
        in_check("stage_type", StageType),
        in_check("result", StageResult),
    )

    application_stage_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    application_id: Mapped[int] = mapped_column(_app_fk())
    stage_type: Mapped[str] = mapped_column(String(255))
    result: Mapped[str | None] = mapped_column(String(255))
    admin_opinion: Mapped[str | None] = mapped_column(Text)
