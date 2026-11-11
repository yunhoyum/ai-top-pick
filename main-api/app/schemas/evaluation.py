"""서류 전형 평가 화면 응답 (화면 17 지원자 순위, 화면 18 결과 보고서)."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class CriteriaRatio(BaseModel):
    criteria_id: int
    name: str
    ratio: int


class WeightedScore(BaseModel):
    criteria_id: int
    weighted: Decimal  # 항목 점수 × 비율 ÷ 100, 소수 첫째 자리


class RankingRow(BaseModel):
    application_id: int
    rank: int | None  # 보고서가 없으면 None
    applicant_name: str | None
    total: Decimal | None  # 소수 첫째 자리
    scores: list[WeightedScore]
    has_opinion: bool
    # '완료'면 보고서가 있다. 그 밖에는 서류 보고서 작업 상태(대기, 실행 중, 실패) 또는 '없음'
    report_status: str


class RankingSummary(BaseModel):
    target_count: int  # 제출했고 필수 기술 미달이 아닌 지원서
    shortfall_count: int
    average: Decimal | None  # 보고서가 있는 지원자의 총점 평균
    opinion_count: int


class RankingOut(BaseModel):
    posting_id: int
    position_name: str | None
    doc_end_at: datetime | None
    criteria: list[CriteriaRatio]
    summary: RankingSummary
    rows: list[RankingRow]  # 총점 내림차순, 보고서가 없는 지원자는 끝에


class ReportScoreOut(BaseModel):
    criteria_id: int
    name: str
    ratio: int
    score: Decimal  # 100점 기준
    weighted: Decimal
    evidence: str  # 채점 이유 (report_score.evidence)


class ReportFitOut(BaseModel):
    talent_content: str
    kind: Literal["기능적", "비기능적"] | None
    evidence: str
    found: bool  # 서류에서 맞는 경험을 찾았는지


class ReportPointOut(BaseModel):
    criteria_name: str | None
    content: str


class ReportOut(BaseModel):
    application_id: int
    posting_id: int
    applicant_name: str | None
    position_name: str | None
    doc_end_at: datetime | None
    total: Decimal
    rank: int
    ranked_count: int  # 보고서가 있어 순위에 든 지원자 수
    summary: str | None
    scores: list[ReportScoreOut]
    fits: list[ReportFitOut]
    strengths: list[ReportPointOut]
    checks: list[ReportPointOut]
    opinion: str | None


class OpinionIn(BaseModel):
    opinion: str | None = Field(default=None, max_length=2000)


class OpinionOut(BaseModel):
    opinion: str | None
