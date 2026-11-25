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

    # ---------- 표정 분석 (vision-server, PC1. SYS-005) ----------
    VISION_URL: str = ""
    # 영상에서 몇 초마다 한 프레임을 볼지 (제안). 60초 영상이 CPU로 약 3초 걸린다 (RAG 설계서 6장)
    VISION_FRAME_INTERVAL_SEC: float = 1.0
    VISION_TIMEOUT_SEC: float = 60.0

    # ---------- 회사 문서 검색 (벡터 DB 설계서 8장) ----------
    # 검색어를 나누는 길이. worker의 CHUNK_MAX_TOKENS와 같게 둔다
    QUERY_MAX_TOKENS: int = 128
    RAG_TOP_K: int = 5
    # 명백히 관계없는 청크만 거른다. ㉠(질문 근거 없음)은 이 값이 아니라 LLM이 판정한다 (RAG 설계서 3.3, E2-v2)
    RAG_MIN_SIMILARITY: float = 0.50
    # 리랭커(embed-server /rerank, bge-reranker-v2-m3). 지금은 질문 생성만 켠다 (RAG 개선 2, 2026-11-20).
    # 벡터 상위 20개를 다시 정렬하고 점수가 기준 미만인 청크를 버린다. 1단계 평가셋 R@1 54.5% → 77.3%
    RAG_RERANK_CANDIDATES: int = 20
    RAG_RERANK_MIN_SCORE: float = 0.005
    # 질문 생성이 LLM에 넘기는 청크 수. 리랭커 R@3(88.6%)가 벡터 R@5(86.4%)보다 높아 3개로 줄인다.
    # 질문당 −4.0초, 사람 판정 품질 차이 없음 (RAG 개선 2, 9.6). 채점은 RAG_TOP_K 그대로
    RAG_QUESTION_TOP_K: int = 3
    # 질문 생성·대체 질문의 리랭커 사용. 시간 비교(scripts/timing-e2e)에서 개선 전 조건을 만들 때만 끈다
    RAG_QUESTION_RERANK: bool = True
    # 주장과 근거 문장의 유사도가 이보다 낮은 근거는 저장하지 않는다. 판정은 바꾸지 않는다 (RAG 설계서 5.5 P11)
    EVIDENCE_MIN_SIMILARITY: float = 0.50
    # 답변 읽기가 뽑은 주장의 글자 2개 묶음 중 답변에 있는 비율이 이보다 낮으면 답변에 없는 주장으로 보고 뺀다.
    # P14~P16 주장 200개: 바꿔 말한 주장은 0.19 이상, 지어낸 주장(A12·A26)은 0.02~0.12였다 (2026-11-18)
    CLAIM_MIN_GROUNDING: float = 0.15
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
