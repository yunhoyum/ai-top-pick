"""문의·예외 처리 응답 (화면 26·26-1, ADM-026·041)."""

from datetime import datetime

from pydantic import BaseModel


class InquiryItem(BaseModel):
    """화면 26 목록 한 줄."""

    inquiry_id: int
    posting_id: int
    position_name: str | None
    application_id: int
    applicant_name: str | None
    question_text: str | None  # 문의 때 진행 중이던 질문
    started_at: datetime | None
    ended_at: datetime | None
    # AI 처리 / AI 미처리 / 관리자 대기 / 관리자 처리 완료
    handling_status: str | None
    cause: str | None  # 시스템 측 / 지원자 측 / 원인 판단 불가
    ai_attempt_count: int


class ChatLine(BaseModel):
    speaker: str | None  # 지원자 / 챗봇
    content: str | None


class LogLineOut(BaseModel):
    logged_at: datetime | None
    content: str | None


class InquiryDetail(InquiryItem):
    """화면 26-1 상세. 처리 내용, 판단 근거, 판단 결과(원인), 후속 조치, AI 시도 조치와 횟수, 대화, 시스템 로그."""

    judgment_basis: str | None
    ai_action: str | None
    handling_detail: str | None
    follow_up: str | None
    handled_at: datetime | None
    messages: list[ChatLine]
    logs: list[LogLineOut]
