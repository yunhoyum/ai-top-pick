"""ai-service(PC2) 내부 API 호출 ('6. 내부 API·WebSocket 규약' 3장). worker가 보고서와 면접 질문을 만들 때 쓴다."""

import httpx

from app.core.config import get_settings


class AiServiceClient:
    def __init__(self, base_url: str | None = None, token: str | None = None, timeout: float | None = None):
        settings = get_settings()
        self._client = httpx.Client(
            base_url=base_url or settings.AI_SERVICE_URL,
            headers={"X-Internal-Token": token or settings.INTERNAL_TOKEN},
            timeout=timeout or settings.AI_SERVICE_TIMEOUT_SEC,
        )

    def create_document_report(self, payload: dict) -> dict:
        """DocumentReportRequest → ReportResult (규약 3.3)."""
        r = self._client.post("/internal/reports/document", json=payload)
        r.raise_for_status()
        return r.json()

    def generate_questions(self, payload: dict) -> dict:
        """QuestionGenRequest → QuestionGenResponse (규약 3.2)."""
        r = self._client.post("/internal/questions/generate", json=payload)
        r.raise_for_status()
        return r.json()


class AsyncAiServiceClient:
    """실시간 면접용 비동기 버전 (코드베이스 1. main-api 9장). WebSocket 처리 중에 쓴다."""

    def __init__(self, base_url: str | None = None, token: str | None = None, timeout: float | None = None):
        settings = get_settings()
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.AI_SERVICE_URL,
            headers={"X-Internal-Token": token or settings.INTERNAL_TOKEN},
            timeout=timeout or settings.AI_SERVICE_TIMEOUT_SEC,
        )

    async def start_interview(self, session_id: int, payload: dict) -> dict:
        """StartInterviewRequest → StartInterviewResponse (규약 2.2)."""
        r = await self._client.post(f"/internal/interview/{session_id}/start", json=payload)
        r.raise_for_status()
        return r.json()

    async def submit_answer(self, session_id: int, payload: dict) -> dict:
        """AnswerRequest → AnswerResponse (규약 2.3)."""
        r = await self._client.post(f"/internal/interview/{session_id}/answer", json=payload)
        r.raise_for_status()
        return r.json()

    async def submit_expression(self, session_id: int, payload: dict) -> dict:
        """ExpressionRequest → ExpressionResponse (규약 2.5)."""
        r = await self._client.post(f"/internal/interview/{session_id}/expression", json=payload)
        r.raise_for_status()
        return r.json()

    async def aclose(self) -> None:
        await self._client.aclose()
