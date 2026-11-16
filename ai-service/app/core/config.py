"""환경변수 설정. 값은 pc2/.env에서 읽는다."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # PC1의 postgres. doc_chunk 읽기에 쓴다
    DATABASE_URL: str
    EMBED_URL: str
    INTERNAL_TOKEN: str
    # tts-server (PC2). 면접 질문 음성 (SYS-011)
    TTS_URL: str = ""
    # 간투사 목록 (ai-service 6장 count_fillers). '그', '저'처럼 뜻이 있는 낱말과 겹치는 것은 넣지 않는다.
    # Deepgram 한국어는 '음'은 남기고 '어'는 빼고 적었다 (2026-11-15 확인, 아키텍처 14)
    FILLER_WORDS: list[str] = ["음", "어", "아", "으", "흠"]
    # STT 보정문과 원문의 글자 유사도가 이보다 낮으면 보정이 답변을 다시 쓴 것으로 보고 원문을 쓴다 (제안).
    # 바른 보정은 0.95 이상, 다시 쓴 보정은 0.35~0.75였다 (2026-11-15 e2e)
    STT_MIN_SIMILARITY: float = 0.85

    # ---------- 표정 분석 (vision-server, PC1. SYS-005) ----------
    VISION_URL: str = ""
    # 영상에서 몇 초마다 한 프레임을 볼지 (제안). 60초 영상이 CPU로 약 3초 걸린다 (RAG 설계서 6장)
    VISION_FRAME_INTERVAL_SEC: float = 1.0
    VISION_TIMEOUT_SEC: float = 60.0

    # ---------- 회사 문서 검색 (벡터 DB 설계서 8장) ----------
    # 검색어를 나누는 길이. worker의 CHUNK_MAX_TOKENS와 같게 둔다
    QUERY_MAX_TOKENS: int = 256
    RAG_TOP_K: int = 5
    # 명백히 관계없는 청크만 거른다. ㉠(질문 근거 없음)은 이 값이 아니라 LLM이 판정한다 (RAG 설계서 3.3, E2-v2)
    RAG_MIN_SIMILARITY: float = 0.50
    # 주장과 근거 문장의 유사도가 이보다 낮은 근거는 저장하지 않는다. 판정은 바꾸지 않는다 (RAG 설계서 5.5 P11)
    EVIDENCE_MIN_SIMILARITY: float = 0.50
    # 면접 보고서 인재상 적합도: LLM이 고른 (인재상 문장, 답변 문장) 짝의 KURE 유사도가 이보다 낮으면 버린다 (제안).
    # 실험 R3: 맞는 짝 0.438~0.559, 분야가 다른 인재상에 억지로 고른 짝 0.268~0.446 (짝 17개라 다시 볼 값)
    FIT_MIN_SIMILARITY: float = 0.43

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
