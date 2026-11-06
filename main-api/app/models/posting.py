from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, in_check
from app.domain.enums import (
    EmploymentType,
    ItemName,
    PostingWriteStatus,
    ProgressStatus,
    StageType,
)


class JobPosting(Base):
    __tablename__ = "job_posting"
    __table_args__ = (
        in_check("employment_type", EmploymentType),
        in_check("progress_status", ProgressStatus),
        in_check("write_status", PostingWriteStatus),
        CheckConstraint("job_question_ratio BETWEEN 0 AND 100", name="job_question_ratio_range"),
        # 일정 순서 (임시 저장 중에는 NULL이 있어 통과한다)
        CheckConstraint("doc_end_at >= doc_start_at", name="doc_end_after_start"),
        CheckConstraint(
            "doc_result_at > doc_end_at AND doc_result_at < interview_start_at",
            name="doc_result_between",
        ),
        CheckConstraint("interview_end_at >= interview_start_at", name="interview_end_after_start"),
        CheckConstraint("interview_result_at > interview_end_at", name="interview_result_after_end"),
    )

    posting_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("member.member_id"))
    position_name: Mapped[str | None] = mapped_column(String(255))
    job_category: Mapped[str | None] = mapped_column(String(255))
    employment_type: Mapped[str | None] = mapped_column(String(255))
    job_description: Mapped[str | None] = mapped_column(Text)
    doc_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    doc_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    doc_result_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interview_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interview_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interview_result_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    functional_talent: Mapped[str | None] = mapped_column(Text)
    nonfunctional_talent: Mapped[str | None] = mapped_column(Text)
    progress_status: Mapped[str | None] = mapped_column(String(255))
    write_status: Mapped[str] = mapped_column(
        String(255), server_default=PostingWriteStatus.DRAFT.value
    )
    question_count: Mapped[int | None] = mapped_column(Integer)
    job_question_ratio: Mapped[int | None] = mapped_column(Integer)
    follow_up_enabled: Mapped[bool | None] = mapped_column(Boolean)
    think_time_sec: Mapped[int | None] = mapped_column(Integer)
    answer_time_sec: Mapped[int | None] = mapped_column(Integer)


class PostingDocument(Base):
    __tablename__ = "posting_document"

    document_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    posting_id: Mapped[int] = mapped_column(ForeignKey("job_posting.posting_id"))
    file_name: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    file_path: Mapped[str] = mapped_column(String(255))
    upload_status: Mapped[str | None] = mapped_column(String(255))


class BasicItem(Base):
    __tablename__ = "basic_item"
    __table_args__ = (in_check("item_name", ItemName),)

    item_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    item_name: Mapped[str] = mapped_column(String(255))
    is_required: Mapped[bool] = mapped_column(Boolean, server_default="false")


class PostingBasicItem(Base):
    __tablename__ = "posting_basic_item"

    posting_id: Mapped[int] = mapped_column(ForeignKey("job_posting.posting_id"), primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("basic_item.item_id"), primary_key=True)


class EvalCriteria(Base):
    __tablename__ = "eval_criteria"
    __table_args__ = (in_check("stage_type", StageType),)

    criteria_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    stage_type: Mapped[str] = mapped_column(String(255))
    criteria_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(255))


class PostingEvalRatio(Base):
    __tablename__ = "posting_eval_ratio"

    posting_id: Mapped[int] = mapped_column(ForeignKey("job_posting.posting_id"), primary_key=True)
    criteria_id: Mapped[int] = mapped_column(
        ForeignKey("eval_criteria.criteria_id"), primary_key=True
    )
    ratio: Mapped[int | None] = mapped_column(Integer)


class Skill(Base):
    __tablename__ = "skill"

    skill_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    skill_name: Mapped[str] = mapped_column(String(255), unique=True)


class RequiredSkill(Base):
    __tablename__ = "required_skill"

    posting_id: Mapped[int] = mapped_column(ForeignKey("job_posting.posting_id"), primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skill.skill_id"), primary_key=True)
    # 자기평가 점수가 이 값 이하면 서류 탈락
    cutoff_score: Mapped[int | None] = mapped_column(Integer)


class EssayTopic(Base):
    __tablename__ = "essay_topic"

    topic_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    posting_id: Mapped[int] = mapped_column(ForeignKey("job_posting.posting_id"))
    seq: Mapped[int] = mapped_column(Integer)
    topic_name: Mapped[str] = mapped_column(String(255))


class CompanyQuestion(Base):
    __tablename__ = "company_question"

    company_question_id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    posting_id: Mapped[int] = mapped_column(ForeignKey("job_posting.posting_id"))
    seq: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
