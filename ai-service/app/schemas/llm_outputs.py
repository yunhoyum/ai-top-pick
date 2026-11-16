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


class RelevanceCheck(BaseModel):
    """답변이 질문에 답했는지 (답변 읽기와 따로 묻는다, 프롬프트 v14)."""

    question_asks: str = Field(min_length=1)  # 질문이 묻는 것 한 문장
    answered: Literal["답함", "일부", "안 함"]


class TopicOutput(BaseModel):
    """질문 주제가 회사 문서에 있는지 (주장 비교와 따로 묻는다)."""

    question_in_docs: bool


# 주장 하나와 회사 문서의 관계. 다섯 단계 중 무엇인지는 코드가 주장들을 모아 정한다 (루브릭 설계서 3.2)
ClaimLevel = Literal["같음", "반대", "문서에 없음"]


class ClaimJudgment(BaseModel):
    """주장 하나를 회사 문서와 비교한 결과 (주장마다 따로 묻는다)."""

    level: ClaimLevel
    evidence_ids: list[str]


# ---------- 서류 보고서 항목 읽기 (회사 자료 없이, 루브릭 설계서 7.3) ----------


class ResumeReadOutput(BaseModel):
    """이력서. LLM 축은 둘 다 회사 자료와 비교하는 축이라 여기서는 주장만 받는다."""

    claims: list[str]
    reason: str = Field(min_length=1)


class SkillCaseReadOutput(ResumeReadOutput):
    problem: Score
    process: Score
    result: Score


class PortfolioReadOutput(ResumeReadOutput):
    decision: Score
    depth: Score


class EssayReadOutput(ResumeReadOutput):
    format: Score
    logic: Score


class SummaryOutput(BaseModel):
    summary: str = Field(min_length=1)


# ---------- 면접 질문 생성 (AI Agent 설계서 2.1) ----------


class QuestionOutput(BaseModel):
    """T-02·T-06 뒤 단계(질문 쓰기)와 T-05·T-08 fallback의 질문 하나."""

    question: str = Field(min_length=1)


class BasePick(BaseModel):
    """T-02·T-06 앞 단계. 바탕이 될 지원자 서류 문장 번호 (프롬프트 v8). 코드가 번호를 확인하고 원문을 꺼낸다."""

    based_on: str | int


class QueryOutput(BaseModel):
    """T-04 고친 검색어."""

    query: str = Field(min_length=1)


class QuestionValidation(BaseModel):
    """T-03·T-07 검증 결과. 통과면 failure_type은 비운다. 인성 질문에는 evidence가 없다 (설계서 3.10)."""

    is_valid: bool
    failure_type: Literal["evidence", "question", "overlap"] | None = None
    feedback: str = ""


class FollowUpValidation(BaseModel):
    """T-12 꼬리질문 검증. 적절성·배타성·부모 질문 반복을 한 번에 본다 (AI Agent 설계서 2.2)."""

    is_valid: bool
    feedback: str = ""


class OverlapCheck(BaseModel):
    """T-03·T-07의 배타성. 확정 질문 하나와 비교한 결과 (프롬프트 v2). 둘 중 하나라도 참이면 겹친다."""

    same_skill: bool
    same_competency: bool
    reason: str = ""
