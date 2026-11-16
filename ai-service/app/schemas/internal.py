"""main-api·worker와 주고받는 본문 ('6. 내부 API·WebSocket 규약'과 같아야 한다)."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

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


# ---------- 3.2 질문 생성 ----------


class QuestionGenRequest(BaseModel):
    application_id: int
    posting: PostingBrief
    documents: ApplicantDocuments
    job_count: int = Field(ge=0)  # calc_question_counts 결과
    personality_count: int = Field(ge=0)


class QuestionGenResponse(BaseModel):
    job: list[str]
    personality: list[str]


# ---------- 3.3 서류 보고서 ----------


class DocumentReportRequest(BaseModel):
    application_id: int
    posting: PostingBrief
    criteria: list[CriteriaItem]  # 서류 4개
    documents: ApplicantDocuments


class AnswerRecord(BaseModel):
    """면접 보고서 입력: 유효 답변 하나 (규약 3.4). 질문 순서대로 보낸다. 점수는 실시간 채점 값이다 (루브릭 설계서 8.2)."""

    question_text: str
    kind: Literal["AI", "꼬리", "기업"]
    corrected_text: str
    answer_score: Decimal | None = None
    content_score: Decimal | None = None  # 내용 채점이 끝까지 실패하면 None
    content_reason: str | None = None
    speech_score: Decimal
    expression_score: Decimal | None = None  # 표정 재분석도 실패하면 None
    main_expression: str | None = None
    expression_ratio: dict[str, float] | None = None
    silence_sec: Decimal
    filler_count: int
    response_delay_sec: Decimal


class InterviewReportRequest(BaseModel):
    application_id: int
    posting: PostingBrief
    criteria: list[CriteriaItem]  # 면접 3개 (내용, 언어, 비언어)
    answers: list[AnswerRecord]  # 유효 답변만


# ---------- 2. 면접 내부 API (main-api → ai-service) ----------


class InterviewSettings(BaseModel):
    follow_up_enabled: bool
    think_time_sec: int
    answer_time_sec: int
    ratios: dict[str, int]  # {"내용": 50, "언어": 30, "비언어": 20}


class QuestionItem(BaseModel):
    qkey: str  # DB 질문은 "q{question_id}", 새 질문은 UUID
    question_id: int | None = None
    kind: Literal["AI", "꼬리", "기업"]
    question_type: Literal["직무", "인성"] | None = None
    parent_qkey: str | None = None  # 꼬리질문의 부모(최상위 기본 질문)
    text: str


class Binding(BaseModel):  # main-api가 새 질문을 저장한 뒤 알려주는 짝
    qkey: str
    question_id: int


class Action(BaseModel):
    type: Literal["present", "remove", "invalidate", "await_expression", "suspend", "end"]
    question: QuestionItem | None = None
    audio_b64: str | None = None  # present일 때 질문 음성(wav)
    keep_question: bool = False  # invalidate일 때: 참이면 질문은 두고 답변만 무효 (기업 질문은 같은 질문을 다시 제시한다)


class StartInterviewRequest(BaseModel):  # 2.2
    session_id: int
    posting_id: int
    resume: bool  # 처음 시작이 아니면 참 (재접속·재시험). 참인데 체크포인트가 없으면 오류
    settings: InterviewSettings
    questions: list[QuestionItem]  # 유효 질문 전체 (직무 → 인성 → 기업)
    posting: PostingBrief
    documents: ApplicantDocuments


class StartInterviewResponse(BaseModel):
    actions: list[Action]


class Word(BaseModel):
    word: str
    start: float  # STT 스트림 기준 초
    end: float


class AnswerRequest(BaseModel):  # 2.3
    qkey: str
    question_id: int
    bindings: list[Binding] = []
    raw_text: str = ""  # Deepgram 원문 (보정 전). 2단계(STT)부터 채운다
    words: list[Word] = []
    answer_start_sec: float = 0.0  # 답변 시간 시작 시점 = 생각 시간 종료
    video_path: str | None = None  # STORAGE_ROOT 기준 상대 경로. 영상이 오지 않으면 None
    end_reason: Literal["button", "silence", "timeout"]


class SttSegment(BaseModel):  # → stt_record
    time_offset_sec: int
    raw_text: str
    corrected_text: str


class AnswerEvaluation(BaseModel):  # → interview_answer (규약 2.3)
    segments: list[SttSegment]
    duration_sec: int
    filler_count: int
    silence_sec: Decimal
    response_delay_sec: Decimal
    main_expression: str | None = None  # 표정 분석이 실패하면 None → actions에 await_expression
    expression_ratio: dict[str, float] | None = None
    content_score: Decimal | None  # 내용 채점이 끝까지 실패하면 None (답변 점수도 None)
    content_reason: str | None
    speech_score: Decimal
    expression_score: Decimal | None = None  # 표정이 없으면 None
    answer_score: Decimal | None = None  # 표정 재분석을 기다리는 중이면 None (/expression이 준다)
    evidence: list[EvidenceSentence] = []


class AnswerResponse(BaseModel):
    evaluation: AnswerEvaluation
    actions: list[Action]


class ExpressionRequest(BaseModel):  # 2.5
    qkey: str
    answer_id: int
    main_expression: str | None = None  # worker가 다시 분석해 저장한 값. 재분석도 실패하면 None
    expression_ratio: dict[str, float] | None = None
    bindings: list[Binding] = []


class ExpressionResponse(BaseModel):
    expression_score: Decimal | None  # 재분석도 실패하면 None
    answer_score: Decimal | None  # 표정이 None이면 내용·발화만으로 계산. 내용 채점이 실패했으면 None
    actions: list[Action]


Cause = Literal["시스템 측", "지원자 측", "원인 판단 불가"]


class LogLine(BaseModel):  # 2.4
    logged_at: str  # ISO 일시. main-api가 만든 그대로 LLM에 보인다
    content: str


class InquiryRequest(BaseModel):  # 2.4
    inquiry_id: int
    # open: 문의 시작 / message: 지원자 메시지 / check: 해결 확인 결과 (시스템 재검사 또는 지원자 확인, 5단계에서 더함)
    event: Literal["open", "message", "check"]
    text: str | None = None
    resolved: bool | None = None  # check일 때만
    system_logs: list[LogLine] = []
    bindings: list[Binding] = []


class Judgment(BaseModel):  # 2.4
    resolved: bool
    cause: Cause
    judgment_basis: str  # → inquiry.judgment_basis
    ai_action: str  # → inquiry.ai_action
    handling_detail: str  # → inquiry.handling_detail
    ai_attempt_count: int  # → inquiry.ai_attempt_count


class InquiryResponse(BaseModel):  # 2.4
    reply: str | None  # 챗봇 답변 → chat_message
    # 해결 확인을 어떻게 받을지. system: 브라우저가 마이크·카메라를 다시 검사해 보낸다 / applicant: 지원자에게 묻는다
    check: Literal["system", "applicant"] | None = None
    judgment: Judgment | None  # 판단이 끝났을 때만 값이 있다
    actions: list[Action]
