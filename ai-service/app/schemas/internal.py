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
    video_path: str = ""  # STORAGE_ROOT 기준 상대 경로. 2단계(영상)부터 채운다
    end_reason: Literal["button", "silence", "timeout"]


class AnswerResponse(BaseModel):
    # 규약은 AnswerEvaluation이다. 실시간 면접 1단계는 평가가 없어 None이다. 3단계(채점)에서 채운다
    evaluation: dict | None = None
    actions: list[Action]
