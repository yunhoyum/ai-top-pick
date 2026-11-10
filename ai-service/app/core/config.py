"""환경변수 설정. 값은 pc2/.env에서 읽는다."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # PC1의 postgres. doc_chunk 읽기에 쓴다
    DATABASE_URL: str
    EMBED_URL: str
    INTERNAL_TOKEN: str

    # ---------- 회사 문서 검색 (벡터 DB 설계서 8장) ----------
    # 검색어를 나누는 길이. worker의 CHUNK_MAX_TOKENS와 같게 둔다
    QUERY_MAX_TOKENS: int = 512
    RAG_TOP_K: int = 5
    # 평가(벡터 DB 설계서 11장) 전까지 쓰는 임시 값이다
    RAG_MIN_SIMILARITY: float = 0.0

    @property
    def sqlalchemy_url(self) -> str:
        """psycopg3 드라이버 접두어를 붙인다. .env에는 postgresql:// 형태로 둔다."""
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            return "postgresql+psycopg://" + url[len("postgresql://"):]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
