from pydantic import BaseModel, Field

from app.schemas.doc_criteria import CriteriaOut, RatioIn

# DB int 범위. 회사의 의도를 존중해 값의 크기는 따로 제한하지 않는다
_INT_MAX = 2_147_483_647


class InterviewCriteriaIn(BaseModel):
    """화면 07 면접 평가기준. 임시 저장 때는 비어 있어도 된다."""

    ratios: list[RatioIn] = []
    question_count: int | None = Field(default=None, ge=0, le=_INT_MAX)
    follow_up_enabled: bool | None = None
    think_time_sec: int | None = Field(default=None, ge=0, le=_INT_MAX)
    answer_time_sec: int | None = Field(default=None, ge=0, le=_INT_MAX)


class InterviewCriteriaOut(BaseModel):
    criteria: list[CriteriaOut]
    question_count: int | None
    follow_up_enabled: bool | None
    think_time_sec: int | None
    answer_time_sec: int | None
