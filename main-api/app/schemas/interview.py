"""AI 화상 면접 요청·응답 (화면 22·23, 코드베이스 1. main-api 6.6)."""

from datetime import datetime

from pydantic import BaseModel


class InterviewGuide(BaseModel):
    """화면 22 AI 화상 면접 안내사항."""

    application_id: int
    position_name: str | None
    question_count: int  # 유효 질문 수 (직무 + 인성 + 기업)
    think_time_sec: int
    answer_time_sec: int
    interview_start_at: datetime | None
    interview_end_at: datetime | None
    interview_result_at: datetime | None  # 화면 25 '면접 합격자 발표 일시'
    # 기술적 테스트(화면 23)로 넘어갈 수 있는지. 아니면 reason에 이유를 준다
    can_enter: bool
    reason: str | None = None


class EnterSessionRequest(BaseModel):
    """화면 23 기술적 테스트 결과 (APP-015)."""

    camera_ok: bool
    mic_ok: bool


class SessionOut(BaseModel):
    session_id: int
    status: str
    # 이미 시작한 응시에 다시 들어왔는지 (재접속)
    resumed: bool


class VideoOut(BaseModel):
    """답변 영상 저장 결과 (APP-016)."""

    video_path: str
