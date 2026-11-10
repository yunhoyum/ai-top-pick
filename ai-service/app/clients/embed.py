"""embed-server(KURE-v1, PC1) 호출. main-api app/clients/embed.py와 같은 동작이다."""

import httpx

from app.core.config import get_settings

# embed-server가 한 번에 받는 글 수 (1~64)
MAX_TEXTS = 64
EMBEDDING_DIM = 1024


class EmbedClient:
    def __init__(self, base_url: str | None = None, token: str | None = None, timeout: float = 30.0):
        settings = get_settings()
        self._client = httpx.Client(
            base_url=base_url or settings.EMBED_URL,
            headers={"X-Internal-Token": token or settings.INTERNAL_TOKEN},
            timeout=timeout,
        )

    def tokenize(self, texts: list[str]) -> list[list[tuple[int, int]]]:
        """글마다 토큰의 [시작, 끝] 글자 위치. 특수 토큰은 들어 있지 않다."""
        offsets: list[list[tuple[int, int]]] = []
        for batch in _batches(texts):
            r = self._client.post("/tokenize", json={"texts": batch})
            r.raise_for_status()
            offsets += [[(s, e) for s, e in item] for item in r.json()["offsets"]]
        return offsets

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for batch in _batches(texts):
            r = self._client.post("/embed", json={"texts": batch})
            r.raise_for_status()
            body = r.json()
            # doc_chunk.embedding은 vector(1024)다 (벡터 DB 설계서 5장)
            if body["dim"] != EMBEDDING_DIM:
                raise ValueError(f"임베딩 차원이 {body['dim']}입니다. {EMBEDDING_DIM}이어야 합니다.")
            vectors += body["vectors"]
        return vectors


def _batches(texts: list[str]):
    for i in range(0, len(texts), MAX_TEXTS):
        yield texts[i : i + MAX_TEXTS]
