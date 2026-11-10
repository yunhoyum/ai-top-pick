"""LLM 클라이언트 (ai-service 7). OpenAI 호환 API로 부른다. 모델을 바꿔도 코드는 그대로다 (아키텍처 4.2)."""

from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from app.core.config import get_settings


def get_chat_model() -> Runnable:
    """JSON만 출력하는 채팅 모델. 출력 형식 검증은 chains/structured.py가 한다."""
    settings = get_settings()
    if not settings.LLM_URL or not settings.LLM_MODEL:
        raise RuntimeError("LLM_URL과 LLM_MODEL을 설정해야 합니다.")
    model = ChatOpenAI(
        base_url=settings.LLM_URL,
        model=settings.LLM_MODEL,
        # Ollama 등 로컬 서버는 키를 검사하지 않지만 클라이언트가 빈 값을 받지 않는다
        api_key="local",
        temperature=settings.LLM_TEMPERATURE,
        timeout=settings.LLM_TIMEOUT_SEC,
    )
    return model.bind(response_format={"type": "json_object"})
