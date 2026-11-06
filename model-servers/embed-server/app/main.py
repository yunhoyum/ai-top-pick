import hmac
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException

from . import model
from .schemas import EmbedRequest, EmbedResponse

INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not INTERNAL_TOKEN:
        raise RuntimeError("INTERNAL_TOKEN이 비어 있습니다. 시작을 거부합니다.")
    model.load()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/embed", response_model=EmbedResponse)
def embed(req: EmbedRequest, x_internal_token: str | None = Header(default=None)):
    if not x_internal_token or not hmac.compare_digest(x_internal_token, INTERNAL_TOKEN):
        raise HTTPException(status_code=401, detail="invalid token")
    vectors = model.encode(req.texts)
    return EmbedResponse(vectors=vectors, dim=len(vectors[0]))
