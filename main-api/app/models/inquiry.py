from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Identity, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, in_check
from app.domain.enums import DefectCause, FollowUpAction, JudgmentCode, Speaker


class JudgmentType(Base):
    __tablename__ = "judgment_type"
    __table_args__ = (
        in_check("judgment_code", JudgmentCode),
        in_check("cause", DefectCause),
        in_check("follow_up", FollowUpAction),
    )

    judgment_code: Mapped[str] = mapped_column(String(255), primary_key=True)
    cause: Mapped[str] = mapped_column(String(255))
    # true: 문의 중 해결, false: 미해결
    ai_handled: Mapped[bool] = mapped_column(Boolean)
    follow_up: Mapped[str | None] = mapped_column(String(255))


class Inquiry(Base):
    __tablename__ = "inquiry"

    inquiry_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_session.session_id"))
    # 문의 시점에 진행 중이던 질문
    question_id: Mapped[int | None] = mapped_column(ForeignKey("interview_question.question_id"))
    judgment_code: Mapped[str | None] = mapped_column(ForeignKey("judgment_type.judgment_code"))
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    judgment_basis: Mapped[str | None] = mapped_column(Text)
    ai_action: Mapped[str | None] = mapped_column(Text)
    handling_detail: Mapped[str | None] = mapped_column(Text)


class ChatMessage(Base):
    __tablename__ = "chat_message"
    __table_args__ = (in_check("speaker", Speaker),)

    message_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    inquiry_id: Mapped[int] = mapped_column(ForeignKey("inquiry.inquiry_id"))
    seq: Mapped[int | None] = mapped_column(Integer)
    speaker: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str | None] = mapped_column(Text)


class SystemLog(Base):
    __tablename__ = "system_log"

    log_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    inquiry_id: Mapped[int] = mapped_column(ForeignKey("inquiry.inquiry_id"))
    logged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    content: Mapped[str | None] = mapped_column(Text)
