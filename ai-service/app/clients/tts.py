"""tts-server(Supertonic-3, PC2) 호출 (ai-service 7장). 질문 제시 때 질문 음성을 만든다 (SYS-011)."""

import httpx

from app.core.config import get_settings


class TtsClient:
    def __init__(self, base_url: str | None = None, token: str | None = None, timeout: float = 30.0):
        settings = get_settings()
        self._client = httpx.Client(
            base_url=base_url or settings.TTS_URL,
            headers={"X-Internal-Token": token or settings.INTERNAL_TOKEN},
            timeout=timeout,
        )

    def synthesize(self, text: str) -> bytes:
        """질문 글을 wav로 바꾼다. 음성 파일은 저장하지 않는다 (SYS-011)."""
        r = self._client.post("/tts", json={"text": text})
        r.raise_for_status()
        return r.content
