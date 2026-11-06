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
