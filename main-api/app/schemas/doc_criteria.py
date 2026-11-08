from pydantic import BaseModel, Field


class RatioIn(BaseModel):
    criteria_id: int
    # 0%도 허용한다. None이면 아직 입력하지 않은 항목이다
    ratio: int | None = Field(default=None, ge=0, le=100)


class DocCriteriaIn(BaseModel):
    """화면 06 서류 평가기준. 임시 저장 때는 비어 있어도 된다."""

    ratios: list[RatioIn] = []


class CriteriaOut(BaseModel):
    criteria_id: int
    criteria_name: str
    description: str | None
    ratio: int | None


class DocCriteriaOut(BaseModel):
    criteria: list[CriteriaOut]
