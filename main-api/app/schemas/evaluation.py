"""전형 평가 화면 응답. 서류: 화면 17 지원자 순위, 18 결과 보고서. 면접: 27 순위, 28 보고서, 29 자료 원본."""

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
    opinion: str | None  # 화면 20 관리자 의견 열
    result: str | None  # 그 전형의 결과 (합격, 불합격). 합격자를 확정하기 전에는 None
    # '완료'면 보고서가 있다. 그 밖에는 보고서 작업 상태(대기, 실행 중, 실패), '없음', 면접은 '미응시'
    report_status: str
    follow_up_count: int | None = None  # 면접만. 받은 유효 꼬리질문 수 (총점에 더하지 않는다)


class RankingSummary(BaseModel):
    target_count: int  # 서류: 제출했고 필수 기술 미달이 아닌 지원서 / 면접: 서류 합격자(면접 대상)
    shortfall_count: int  # 면접은 0
    taken_count: int | None = None  # 면접만. 응시 완료
    average: Decimal | None  # 보고서가 있는 지원자의 총점 평균
    opinion_count: int


class RankingOut(BaseModel):
    posting_id: int
    position_name: str | None
    doc_end_at: datetime | None
    interview_end_at: datetime | None = None
    criteria: list[CriteriaRatio]
    confirmed: bool  # 그 전형의 합격자를 확정했는지 (ADM-025, ADM-031)
    summary: RankingSummary
    rows: list[RankingRow]  # 총점 내림차순, 보고서가 없는 지원자는 끝에


class ReportScoreOut(BaseModel):
    criteria_id: int
    name: str
    ratio: int
    score: Decimal  # 100점 기준
    weighted: Decimal
    # 면접 보고서에 없는 항목(비언어)이 있어 남은 비율을 합 100으로 늘렸으면 늘린 비율. 아니면 None
    scaled_ratio: Decimal | None = None
    evidence: str  # 채점 이유 (report_score.evidence)


class ReportFitOut(BaseModel):
    talent_content: str
    kind: Literal["기능적", "비기능적"] | None
    evidence: str
    found: bool  # 서류에서 맞는 경험을 찾았는지


class ReportPointOut(BaseModel):
    criteria_name: str | None
    content: str


class QuestionResultOut(BaseModel):
    """화면 28 질문별 결과 (SYS-010). 질문 구분과 주요 표정. 답변 기록은 화면 29에서 본다."""

    seq: int  # 1부터. 진행 목록 순서
    question_id: int
    text: str
    kind: Literal["AI", "꼬리", "기업"]
    main_expression: str | None
    answer_id: int


class ReportOut(BaseModel):
    application_id: int
    posting_id: int
    applicant_name: str | None
    position_name: str | None
    doc_end_at: datetime | None
    interview_end_at: datetime | None = None
    total: Decimal
    rank: int
    ranked_count: int  # 보고서가 있어 순위에 든 지원자 수
    summary: str | None
    scores: list[ReportScoreOut]
    fits: list[ReportFitOut]
    strengths: list[ReportPointOut]
    checks: list[ReportPointOut]
    opinion: str | None
    questions: list[QuestionResultOut] = []  # 면접만
    follow_up_count: int | None = None  # 면접만


class OpinionIn(BaseModel):
    opinion: str | None = Field(default=None, max_length=2000)


class OpinionOut(BaseModel):
    opinion: str | None


class PassIn(BaseModel):
    """화면 20 합격자 확정. 고른 지원서는 합격, 나머지 평가 대상은 불합격이다 (ADM-025)."""

    application_ids: list[int] = Field(min_length=1)


class PassOut(BaseModel):
    passed: int
    failed: int


# ---------- 화면 19 지원자 자료 원본 (ADM-022) ----------


class SourceEducation(BaseModel):
    school_name: str | None
    major: str | None
    period: str | None


class SourceCareer(BaseModel):
    company_name: str | None
    job_role: str | None
    period: str | None


class SourceProject(BaseModel):
    project_name: str | None
    period: str | None
    description: str | None


class SourceSkill(BaseModel):
    skill_name: str
    score: int | None


class SourceCase(BaseModel):
    skill_name: str | None
    content: str | None


class SourceEssay(BaseModel):
    topic: str
    content: str | None


class SourcePortfolio(BaseModel):
    file_name: str
    file_size: int | None


class SourceDocumentsOut(BaseModel):
    application_id: int
    posting_id: int
    position_name: str | None
    doc_end_at: datetime | None
    name: str | None
    phone: str | None
    email: str | None
    educations: list[SourceEducation]
    careers: list[SourceCareer]
    projects: list[SourceProject]
    skills: list[SourceSkill]
    cases: list[SourceCase]
    essays: list[SourceEssay]
    portfolio: SourcePortfolio | None


# ---------- 화면 29 지원자 자료 원본 (면접, ADM-028) ----------


class SttLineOut(BaseModel):
    time_offset_sec: int | None
    corrected_text: str | None
    raw_text: str | None  # 보정문과 다르면 화면이 'LLM 수정'과 원문을 함께 보인다


class InterviewSourceQuestion(BaseModel):
    seq: int
    question_id: int
    text: str
    kind: Literal["AI", "꼬리", "기업"]
    answer_id: int
    duration_sec: int | None
    has_video: bool
    stt: list[SttLineOut]


class InterviewSourceOut(BaseModel):
    application_id: int
    posting_id: int
    position_name: str | None
    interview_end_at: datetime | None
    name: str | None
    questions: list[InterviewSourceQuestion]
