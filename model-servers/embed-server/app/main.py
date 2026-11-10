import hmac
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException

from . import model
from .schemas import EmbedRequest, EmbedResponse, TokenizeRequest, TokenizeResponse

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


def _check_token(x_internal_token: str | None) -> None:
    if not x_internal_token or not hmac.compare_digest(x_internal_token, INTERNAL_TOKEN):
        raise HTTPException(status_code=401, detail="invalid token")


@app.post("/embed", response_model=EmbedResponse)
def embed(req: EmbedRequest, x_internal_token: str | None = Header(default=None)):
    _check_token(x_internal_token)
    vectors = model.encode(req.texts)
    return EmbedResponse(vectors=vectors, dim=len(vectors[0]))


@app.post("/tokenize", response_model=TokenizeResponse)
def tokenize(req: TokenizeRequest, x_internal_token: str | None = Header(default=None)):
    _check_token(x_internal_token)
    return TokenizeResponse(offsets=model.tokenize(req.texts))
