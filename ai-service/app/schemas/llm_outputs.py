"""LLM 출력 모델. invoke_structured가 이 모델로 검증한다."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

Score = Annotated[int, Field(ge=0, le=100)]


class AnswerReadOutput(BaseModel):
    """면접 답변 읽기 (회사 문서 없이). 회사 문서와 상관없는 두 축과 지원자가 말한 것을 낸다."""

    claims: list[str]
    relevance: Score
    specificity: Score
    reason: str = Field(min_length=1)


class TopicOutput(BaseModel):
    """질문 주제가 회사 문서에 있는지 (주장 비교와 따로 묻는다)."""

    question_in_docs: bool


# 주장 하나와 회사 문서의 관계. 다섯 단계 중 무엇인지는 코드가 주장들을 모아 정한다 (루브릭 설계서 3.2)
ClaimLevel = Literal["같음", "일부만 같음", "반대", "문서에 없음"]


class ClaimJudgment(BaseModel):
    """주장 하나를 회사 문서와 비교한 결과 (주장마다 따로 묻는다)."""

    level: ClaimLevel
    evidence_ids: list[str]
