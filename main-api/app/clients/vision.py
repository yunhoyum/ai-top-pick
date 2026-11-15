"""vision-server(DeepFace, PC1) 호출. 표정 분석이 실패한 답변을 worker가 다시 분석할 때 쓴다 (Celery 4장)."""

import httpx

from app.core.config import get_settings


class VisionClient:
    def __init__(self, base_url: str | None = None, token: str | None = None, timeout: float = 120.0):
        settings = get_settings()
        self._client = httpx.Client(
            base_url=base_url or settings.VISION_URL,
            headers={"X-Internal-Token": token or settings.INTERNAL_TOKEN},
            timeout=timeout,
        )

    def analyze(self, video_path: str) -> list[dict]:
        """프레임별 감정 [{t, emotion, scores}]. 얼굴을 찾지 못한 프레임은 빠진다."""
        interval = get_settings().VISION_FRAME_INTERVAL_SEC
        r = self._client.post("/analyze", json={"video_path": video_path, "frame_interval_sec": interval})
        r.raise_for_status()
        return r.json()["frames"]
