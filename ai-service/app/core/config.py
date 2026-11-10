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
    QUERY_MAX_TOKENS: int = 256
    RAG_TOP_K: int = 5
    # 명백히 관계없는 청크만 거른다. ㉠(질문 근거 없음)은 이 값이 아니라 LLM이 판정한다 (RAG 설계서 3.3, E2-v2)
    RAG_MIN_SIMILARITY: float = 0.50
    # 주장과 근거 문장의 유사도가 이보다 낮은 근거는 저장하지 않는다. 판정은 바꾸지 않는다 (RAG 설계서 5.5 P11)
    EVIDENCE_MIN_SIMILARITY: float = 0.50

    # ---------- LLM (OpenAI 호환 API, 아키텍처 4.2) ----------
    LLM_URL: str = ""
    LLM_MODEL: str = ""
    # 같은 입력에 같은 점수가 나오게 고정한다 (RAG 설계서 5.1)
    LLM_TEMPERATURE: float = 0.0
    LLM_TIMEOUT_SEC: float = 120.0
    # 출력이 형식 검증을 통과하지 못하면 다시 묻는 횟수 (아키텍처 9.4)
    LLM_MAX_RETRIES: int = 2

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
