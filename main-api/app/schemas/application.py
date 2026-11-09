from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def _strip(v: str | None) -> str | None:
    return v.strip() if isinstance(v, str) else v


class _Stripped(BaseModel):
    """문자열 입력은 앞뒤 공백을 지운다."""

    @field_validator("*", mode="before")
    @classmethod
    def strip_text(cls, v):
        return _strip(v)


# ---------- 입력 ----------
class ProfileIO(_Stripped):
    name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)


class EducationIO(_Stripped):
    school_name: str | None = Field(default=None, max_length=255)
    major: str | None = Field(default=None, max_length=255)
    # 'YYYY.MM ~ YYYY.MM'. 재학·재직 중이면 종료를 비운다 ('YYYY.MM ~')
    period: str | None = Field(default=None, max_length=50)


class CareerIO(_Stripped):
    company_name: str | None = Field(default=None, max_length=255)
    job_role: str | None = Field(default=None, max_length=255)
    period: str | None = Field(default=None, max_length=50)


class ProjectIO(_Stripped):
    project_name: str | None = Field(default=None, max_length=255)
    period: str | None = Field(default=None, max_length=50)
    description: str | None = None


class ResumeIn(BaseModel):
    """화면 12 이력서"""

    profile: ProfileIO
    educations: list[EducationIO] = []
    careers: list[CareerIO] = []
    projects: list[ProjectIO] = []


class SkillScoreIn(_Stripped):
    skill_name: str = Field(min_length=1, max_length=255)
    # 1~5점. 임시 저장 때는 비어 있어도 된다
    score: int | None = Field(default=None, ge=1, le=5)


class SkillCaseIn(_Stripped):
    skill_name: str | None = Field(default=None, max_length=255)
    content: str | None = None


class SkillsIn(BaseModel):
    """화면 13 사용기술, 기술 적용 사례. 필수 기술 외에 직접 추가한 기술도 담는다."""

    skills: list[SkillScoreIn] = []
    cases: list[SkillCaseIn] = []


class EssayIn(_Stripped):
    topic_id: int
    content: str | None = None


class EssaysIn(BaseModel):
    """화면 14 자기소개서"""

    essays: list[EssayIn] = []


# ---------- 출력 ----------
class PostingBrief(BaseModel):
    posting_id: int
    position_name: str | None
    progress_status: str | None
    doc_end_at: datetime | None
    doc_result_at: datetime | None


class EssayTopicOut(BaseModel):
    topic_id: int
    topic_name: str


class FormOut(BaseModel):
    """공고가 정한 지원서 구성"""

    has_education: bool
    has_career: bool
    has_project: bool
    essay_topics: list[EssayTopicOut]


class SkillScoreOut(BaseModel):
    skill_name: str
    # 공고의 필수 기술이면 True, 지원자가 직접 추가했으면 False
    required: bool
    score: int | None


class SkillCaseOut(BaseModel):
    skill_name: str | None
    content: str | None


class EssayOut(BaseModel):
    topic_id: int
    content: str | None


class PortfolioOut(BaseModel):
    file_name: str
    file_size: int | None


class ApplicationOut(BaseModel):
    posting: PostingBrief
    form: FormOut
    # 관리자가 지원자 화면을 미리 보는 경우. 저장할 수 없다
    preview: bool
    # '임시 저장'/'제출'. 미리보기는 None
    write_status: str | None
    submitted_at: datetime | None
    profile: ProfileIO
    educations: list[EducationIO]
    careers: list[CareerIO]
    projects: list[ProjectIO]
    skills: list[SkillScoreOut]
    cases: list[SkillCaseOut]
    essays: list[EssayOut]
    portfolio: PortfolioOut | None
