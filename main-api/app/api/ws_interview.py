from fastapi import APIRouter, WebSocket

from app.clients.ai_service import AsyncAiServiceClient
from app.realtime.deepgram_relay import DeepgramRelay
from app.realtime.interview_ws import InterviewSocketHandler

router = APIRouter()


def get_ai_client() -> AsyncAiServiceClient:
    """테스트가 가짜로 바꾼다."""
    return AsyncAiServiceClient()


def get_relay_factory():
    """테스트가 가짜로 바꾼다."""
    return DeepgramRelay


@router.websocket("/ws/interview/{session_id}")
async def interview_socket(ws: WebSocket, session_id: int):
    """APP-016, SYS-011 화면 24 면접 진행 (내부 API 규약 1장)."""
    ai = get_ai_client()
    try:
        await InterviewSocketHandler(ws, session_id, ai, get_relay_factory()).run()
    finally:
        await ai.aclose()
