from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, in_check
from app.domain.enums import Emotion, QuestionType, SessionStatus, ValidStatus


class InterviewQuestion(Base):
    __tablename__ = "interview_question"
    __table_args__ = (
        in_check("question_type", QuestionType),
        in_check("question_status", ValidStatus),
    )

    question_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("application.application_id"))
    # 꼬리질문일 때만 값이 있다. 꼬리질문이 시작된 최상위 기본 질문을 가리킨다
    parent_question_id: Mapped[int | None] = mapped_column(
        ForeignKey("interview_question.question_id")
    )
    # 기업 질문일 때만 값이 있다
    company_question_id: Mapped[int | None] = mapped_column(
        ForeignKey("company_question.company_question_id")
    )
    question_type: Mapped[str | None] = mapped_column(String(255))
    seq: Mapped[int | None] = mapped_column(Integer)
    # 기업 질문이면 NULL (company_question.content 사용)
    content: Mapped[str | None] = mapped_column(Text)
    is_revealed: Mapped[bool | None] = mapped_column(Boolean)
    question_status: Mapped[str] = mapped_column(String(255), server_default=ValidStatus.VALID.value)


class InterviewSession(Base):
    __tablename__ = "interview_session"
    __table_args__ = (in_check("status", SessionStatus),)

    session_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("application.application_id"))
    camera_checked: Mapped[bool | None] = mapped_column(Boolean)
    mic_checked: Mapped[bool | None] = mapped_column(Boolean)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(255), server_default=SessionStatus.IN_PROGRESS.value)
    attempt_no: Mapped[int | None] = mapped_column(Integer)


class InterviewAnswer(Base):
    __tablename__ = "interview_answer"
    __table_args__ = (
        # 같은 응시·질문에 유효한 답변은 1개
        Index(
            "uq_interview_answer_valid",
            "session_id",
            "question_id",
            unique=True,
            postgresql_where=text("answer_status = '유효'"),
        ),
        in_check("main_expression", Emotion),
        in_check("answer_status", ValidStatus),
        CheckConstraint("response_delay_sec >= 0", name="response_delay_range"),
        CheckConstraint("silence_sec >= 0", name="silence_range"),
        CheckConstraint("filler_count >= 0", name="filler_count_range"),
        CheckConstraint("answer_score BETWEEN 0 AND 100", name="answer_score_range"),
    )

    answer_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_session.session_id"))
    question_id: Mapped[int] = mapped_column(ForeignKey("interview_question.question_id"))
    video_path: Mapped[str | None] = mapped_column(String(255))
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    main_expression: Mapped[str | None] = mapped_column(String(255))
    # 감정별 프레임 비율. 예: {"neutral": 0.6, "fear": 0.4}
    expression_ratio: Mapped[dict | None] = mapped_column(JSONB)
    response_delay_sec: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    silence_sec: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    filler_count: Mapped[int | None] = mapped_column(Integer)
    answer_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    answer_status: Mapped[str] = mapped_column(String(255), server_default=ValidStatus.VALID.value)


class SttRecord(Base):
    __tablename__ = "stt_record"

    stt_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    answer_id: Mapped[int] = mapped_column(ForeignKey("interview_answer.answer_id"))
    time_offset_sec: Mapped[int | None] = mapped_column(Integer)
    corrected_text: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)
