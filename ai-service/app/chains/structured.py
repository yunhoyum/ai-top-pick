"""LLM 출력을 Pydantic으로 검증하고, 실패하면 오류를 알려 다시 묻는다 (아키텍처 9.4)."""

from typing import TypeVar

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import Runnable
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings

T = TypeVar("T", bound=BaseModel)


class StructuredOutputError(Exception):
    """재시도해도 출력이 형식 검증을 통과하지 못했다."""


def invoke_structured(
    model: Runnable, messages: list[BaseMessage], schema: type[T], max_retries: int | None = None
) -> T:
    if max_retries is None:
        max_retries = get_settings().LLM_MAX_RETRIES
    messages = list(messages)
    error: ValidationError | None = None
    for _ in range(max_retries + 1):
        content = model.invoke(messages).content
        try:
            return schema.model_validate_json(content)
        except ValidationError as e:
            error = e
            # temperature가 0이라 같은 질문은 같은 답을 낸다. 틀린 출력과 이유를 붙여 다시 묻는다
            messages += [
                AIMessage(content=content),
                HumanMessage(content=f"출력이 형식에 맞지 않습니다. 오류: {e.errors(include_url=False)}\n형식에 맞는 JSON만 다시 출력하세요."),
            ]
    raise StructuredOutputError(f"{max_retries + 1}번 시도했지만 형식 검증에 실패했습니다: {error}")
