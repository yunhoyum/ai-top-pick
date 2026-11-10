"""LLM 출력 모델. invoke_structured가 이 모델로 검증한다."""

from typing import Annotated

from pydantic import BaseModel, Field

Score = Annotated[int, Field(ge=0, le=100)]


class AnswerContentOutput(BaseModel):
    """면접 답변 내용 채점 (루브릭 설계서 3.4). 출력 순서: 질문 주제 판정 → 근거 번호 → 세 축 → 이유."""

    question_in_docs: bool
    evidence_ids: list[str]
    relevance: Score
    specificity: Score
    doc_match: Score
    reason: str = Field(min_length=1)


class AnswerContentNoDocOutput(BaseModel):
    """질문 검색 결과가 비었을 때(㉠). 회사 문서 없이 두 축만 매긴다."""

    relevance: Score
    specificity: Score
    reason: str = Field(min_length=1)
