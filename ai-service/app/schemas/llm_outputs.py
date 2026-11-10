"""LLM 출력 모델. invoke_structured가 이 모델로 검증한다."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

Score = Annotated[int, Field(ge=0, le=100)]


class AnswerReadOutput(BaseModel):
    """면접 답변 읽기 (1번 호출, 회사 문서 없이). 회사 문서와 상관없는 두 축과 지원자가 말한 것을 낸다."""

    claims: list[str]
    relevance: Score
    specificity: Score
    reason: str = Field(min_length=1)


# 주장 하나와 회사 문서의 관계. 다섯 단계 중 무엇인지는 코드가 주장들을 모아 정한다 (루브릭 설계서 3.2)
ClaimLevel = Literal["같음", "반대", "문서에 없음"]


class ClaimMatch(BaseModel):
    # 1번 호출의 claims 순번(1부터). EXAONE이 번호 대신 주장 문장을 쓰기도 해서 문장도 받는다.
    # 문장이면 코드가 claims와 맞춰 본다 (RAG 설계서 5.5 P8)
    claim: int | str
    evidence_ids: list[str]
    level: ClaimLevel


class DocMatchOutput(BaseModel):
    """회사 문서 비교 (2번 호출). 원래 답변이 아니라 1번 호출이 뽑은 주장만 받는다."""

    question_in_docs: bool
    matches: list[ClaimMatch]
