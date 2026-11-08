from pydantic import BaseModel, Field, field_validator


class CompanyQuestionsIn(BaseModel):
    """화면 08 기업 질문과 AI 질문 비율. 임시 저장 때는 비어 있어도 된다."""

    questions: list[str] = []
    # AI 생성 질문 중 직무 질문 비율(%). 인성 질문 비율은 100에서 뺀 값이다
    job_question_ratio: int | None = Field(default=None, ge=0, le=100)

    @field_validator("questions")
    @classmethod
    def strip_questions(cls, v: list[str]) -> list[str]:
        return [q.strip() for q in v]


class CompanyQuestionsOut(BaseModel):
    questions: list[str]
    job_question_ratio: int | None
    # 화면 07에서 정한 출제 문제 개수. 아직 입력하지 않았으면 None
    question_count: int | None
