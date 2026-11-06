import hmac
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException

from . import analyzer
from .frames import VideoNotFound, VideoPathError, VideoUnreadable, resolve_video
from .schemas import AnalyzeRequest, AnalyzeResponse

INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not INTERNAL_TOKEN:
        raise RuntimeError("INTERNAL_TOKEN이 비어 있습니다. 시작을 거부합니다.")
    analyzer.load()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


# CPU를 오래 쓰므로 def(동기)로 둔다. FastAPI가 스레드풀에서 실행해 이벤트 루프를 막지 않는다
@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest, x_internal_token: str | None = Header(default=None)):
    if not x_internal_token or not hmac.compare_digest(x_internal_token, INTERNAL_TOKEN):
        raise HTTPException(status_code=401, detail="invalid token")
    try:
        path = resolve_video(req.video_path)
    except VideoPathError:
        raise HTTPException(status_code=400, detail="invalid video_path")
    except VideoNotFound:
        raise HTTPException(status_code=404, detail="video not found")
    try:
        frames, skipped = analyzer.analyze_video(path, req.frame_interval_sec)
    except VideoUnreadable as e:
        raise HTTPException(status_code=422, detail=str(e))
    return AnalyzeResponse(frames=frames, analyzed=len(frames), skipped=skipped)
