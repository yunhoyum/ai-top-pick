from pydantic import BaseModel, Field

EMOTIONS = ("angry", "disgust", "fear", "happy", "sad", "surprise", "neutral")


class AnalyzeRequest(BaseModel):
    # STORAGE_ROOT 기준 상대 경로. 예: interviews/12/345.webm
    video_path: str = Field(min_length=1, max_length=512)
    frame_interval_sec: float = Field(default=1.0, ge=0.2, le=10.0)


class FrameEmotion(BaseModel):
    t: float
    emotion: str
    scores: dict[str, float]  # 7가지 감정, 합이 1.0


class AnalyzeResponse(BaseModel):
    frames: list[FrameEmotion]
    analyzed: int
    skipped: int  # 얼굴을 찾지 못한 프레임 수
