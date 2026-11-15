"""vision-server(DeepFace, PC1) 호출 (ai-service 7장). 답변 영상의 프레임별 감정을 받는다 (SYS-005).

영상은 PC1 디스크에 있다. 경로(STORAGE_ROOT 기준)만 보내고 vision-server가 직접 읽는다.
"""

import httpx

from app.core.config import get_settings


class VisionClient:
    def __init__(self, base_url: str | None = None, token: str | None = None, timeout: float | None = None):
        settings = get_settings()
        self._client = httpx.Client(
            base_url=base_url or settings.VISION_URL,
            headers={"X-Internal-Token": token or settings.INTERNAL_TOKEN},
            timeout=timeout or settings.VISION_TIMEOUT_SEC,
        )

    def analyze(self, video_path: str, frame_interval_sec: float | None = None) -> list[dict]:
        """프레임별 감정 [{t, emotion, scores}]. 얼굴을 찾지 못한 프레임은 빠진다."""
        interval = frame_interval_sec or get_settings().VISION_FRAME_INTERVAL_SEC
        r = self._client.post("/analyze", json={"video_path": video_path, "frame_interval_sec": interval})
        r.raise_for_status()
        return r.json()["frames"]
