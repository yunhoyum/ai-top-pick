from pydantic import BaseModel, Field, field_validator


class SkillIn(BaseModel):
    skill_name: str = Field(max_length=255)
    # 자기평가 점수가 이 값 이하면 서류 탈락. None이면 탈락 기준 없음 (5점 척도라 1~4)
    cutoff_score: int | None = Field(default=None, ge=1, le=4)

    @field_validator("skill_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class DocItemsIn(BaseModel):
    """화면 05 서류 작성 문항. 임시 저장 때는 비어 있어도 된다."""

    basic_item_ids: list[int] = []
    skills: list[SkillIn] = []
    essay_topics: list[str] = []

    @field_validator("essay_topics")
    @classmethod
    def strip_topics(cls, v: list[str]) -> list[str]:
        return [t.strip() for t in v]


class BasicItemOut(BaseModel):
    item_id: int
    item_name: str
    is_required: bool
    selected: bool


class SkillOut(BaseModel):
    skill_name: str
    cutoff_score: int | None


class DocItemsOut(BaseModel):
    basic_items: list[BasicItemOut]
    skills: list[SkillOut]
    essay_topics: list[str]
