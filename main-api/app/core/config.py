"""환경변수 설정. DB 주소, JWT 비밀키 등은 코드에 쓰지 않고 .env에서 읽는다."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # compose는 env_file로 환경변수를 주입한다. 로컬 실행 때는 main-api/.env 도 읽는다
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---------- 필수: 없으면 앱이 뜨지 않는다 ----------
    DATABASE_URL: str
    JWT_SECRET: str

    # ---------- 인증 ----------
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MIN: int = 60

    # ---------- 파일 저장 ----------
    STORAGE_ROOT: str = "/data/storage"
    MAX_PDF_MB: int = 20

    # ---------- 회사 문서 임베딩 (벡터 DB 설계서 4장) ----------
    EMBED_URL: str = "http://embed-server:8000"
    INTERNAL_TOKEN: str = ""
    # 검색 평가 E2에서 정했다 (RAG 설계서 5.5). embed-server 입력 한도(EMBED_MAX_SEQ_LEN 512)보다 크면 안 된다
    CHUNK_MAX_TOKENS: int = 256
    CHUNK_OVERLAP_TOKENS: int = 64

    # ---------- CORS: 쉼표로 구분. 쿠키 인증이라 와일드카드는 쓸 수 없다 ----------
    CORS_ORIGINS: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

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
