"""main-api·worker와 주고받는 본문 ('6. 내부 API·WebSocket 규약'과 같아야 한다)."""

from pydantic import BaseModel


class PostingBrief(BaseModel):
    posting_id: int
    position_name: str
    job_description: str
    functional_talent: str
    nonfunctional_talent: str


class ApplicantDocuments(BaseModel):
    personal: dict  # 인적사항. 점수에 넣지 않는다 (루브릭 설계서 7.3)
    skills: list[dict]  # skill_name, self_score(1~5)
    educations: list[dict]  # 공고가 고른 문항만
    careers: list[dict]
    projects: list[dict]
    skill_cases: list[str]
    essays: list[dict]  # topic, content
    portfolio_text: str | None = None
