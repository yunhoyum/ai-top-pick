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
    # 답변 영상 1개 크기 상한 (제안)
    MAX_VIDEO_MB: int = 200

    # ---------- 실시간 면접 (아키텍처 7, 7.1) ----------
    # Deepgram 키는 main-api만 가진다. 브라우저 음성은 main-api가 중계한다
    DEEPGRAM_API_KEY: str = ""
    DEEPGRAM_URL: str = "wss://api.deepgram.com/v1/listen"
    # 한국어 확인(2026-11-15): nova-3·nova-2 모두 동작. nova-3는 문장부호를 붙인다
    DEEPGRAM_MODEL: str = "nova-3"
    # 첫 단어 이후 이만큼 말이 없으면 답변을 끝낸다 (APP-016)
    SILENCE_END_SEC: float = 10.0
    # 답변이 끝난 뒤 영상 업로드를 기다리는 최대 시간 (제안). 넘기면 영상 없이 진행한다
    VIDEO_UPLOAD_WAIT_SEC: float = 60.0
    # 표정 분석이 실패한 답변을 worker가 다시 분석할 때까지 기다리는 최대 시간 (제안). 넘기면 표정 없이 채점한다
    EXPRESSION_WAIT_SEC: float = 60.0

    # ---------- 표정 분석 (vision-server, PC1. worker가 다시 분석할 때 직접 부른다) ----------
    VISION_URL: str = "http://vision-server:8000"
    # ai-service의 VISION_FRAME_INTERVAL_SEC와 같게 둔다
    VISION_FRAME_INTERVAL_SEC: float = 1.0

    # ---------- 회사 문서 임베딩 (벡터 DB 설계서 4장) ----------
    EMBED_URL: str = "http://embed-server:8000"
    INTERNAL_TOKEN: str = ""
    # 검색 평가 E2에서 정했다 (RAG 설계서 5.5). embed-server 입력 한도(EMBED_MAX_SEQ_LEN 512)보다 크면 안 된다
    CHUNK_MAX_TOKENS: int = 128
    CHUNK_OVERLAP_TOKENS: int = 32

    # ---------- ai-service (PC2) ----------
    AI_SERVICE_URL: str = ""
    # 서류 보고서는 지원자 1명에 LLM을 20번 넘게 부른다. EXAONE으로 1~3분 걸렸다 (RAG 설계서 5.8)
    AI_SERVICE_TIMEOUT_SEC: float = 600.0

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
