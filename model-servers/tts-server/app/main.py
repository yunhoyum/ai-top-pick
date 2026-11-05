import os
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Response

from app.model import tts_model
from app.schemas import TTSRequest

INTERNAL_TOKEN = os.environ["INTERNAL_TOKEN"]


def verify_token(x_internal_token: str | None = Header(default=None)):
    if x_internal_token is None or not secrets.compare_digest(x_internal_token, INTERNAL_TOKEN):
        raise HTTPException(status_code=401, detail="invalid internal token")


@asynccontextmanager
async def lifespan(app: FastAPI):
    tts_model.load()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/tts", dependencies=[Depends(verify_token)])
def tts(req: TTSRequest):
    """SYS-011 질문 음성 변환(TTS)"""
    audio = tts_model.synthesize(req.text)
    return Response(content=audio, media_type="audio/wav")