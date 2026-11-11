"""ai-service(PC2) 내부 API 호출 ('6. 내부 API·WebSocket 규약' 3장). worker가 보고서를 만들 때 쓴다."""

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
