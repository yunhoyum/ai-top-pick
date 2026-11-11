"""main-api·worker와 주고받는 본문 ('6. 내부 API·WebSocket 규약'과 같아야 한다)."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

# ---------- 3.1 공통 타입 ----------


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


class CriteriaItem(BaseModel):
    criteria_id: int
    name: str  # 이력서, 기술 적용 사례, ... / 내용, 언어, 비언어
    description: str | None = None
    ratio: int


class EvidenceSentence(BaseModel):  # → evidence_sentence (벡터 DB 설계서 8.4)
    source_type: Literal["기능적 인재상", "비기능적 인재상", "직무 설명", "프로젝트 문서"]
    source_id: int | None = None  # 프로젝트 문서만 document_id
    chunk_id: int | None = None  # 프로젝트 문서만
    sentence: str  # 원문 문장 사본


class CriteriaScore(BaseModel):  # → report_score
    criteria_id: int
    score: Decimal  # 100점 기준. 비율은 곱하지 않는다
    evidence: str
    evidence_sentences: list[EvidenceSentence]  # → evidence_sentence(report_id, criteria_id)


class FitItem(BaseModel):  # → report_fit
    talent_content: str
    evidence: str


class PointItem(BaseModel):  # → report_point
    point_type: Literal["강점", "확인 필요"]
    criteria_id: int | None = None
    content: str


class ReportResult(BaseModel):
    scores: list[CriteriaScore]
    fits: list[FitItem]
    points: list[PointItem]
    summary: str  # → stage_report.ai_summary


# ---------- 3.3 서류 보고서 ----------


class DocumentReportRequest(BaseModel):
    application_id: int
    posting: PostingBrief
    criteria: list[CriteriaItem]  # 서류 4개
    documents: ApplicantDocuments
