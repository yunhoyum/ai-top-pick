"""상태 값. 값은 테이블 명세서의 한글 값을 그대로 DB에 저장한다."""

from enum import Enum


class Role(str, Enum):
    ADMIN = "관리자"
    APPLICANT = "지원자"


class EmploymentType(str, Enum):
    REGULAR = "정규직"
    CONTRACT = "계약직"


class ProgressStatus(str, Enum):
    BEFORE_RECRUIT = "모집 전"
    DOC_RECEIVING = "서류 접수 중"
    DOC_EVALUATION = "서류 평가"
    INTERVIEW_ONGOING = "면접 진행"
    INTERVIEW_EVALUATION = "면접 평가"
    CLOSED = "마감"


class PostingWriteStatus(str, Enum):
    DRAFT = "임시 저장"
    COMPLETE = "등록 완료"


class ApplicationWriteStatus(str, Enum):
    DRAFT = "임시 저장"
    SUBMITTED = "제출"


class ItemName(str, Enum):
    PROFILE = "인적사항"
    EDUCATION = "학력"
    CAREER = "경력"
    PROJECT = "프로젝트"
    SKILL_CASE = "기술 적용 사례"


class StageType(str, Enum):
    DOCUMENT = "서류"
    INTERVIEW = "면접"


class StageResult(str, Enum):
    PASS = "합격"
    FAIL = "불합격"
    SKILL_SHORTFALL = "필수 기술 미달"


class QuestionType(str, Enum):
    JOB = "직무"
    PERSONALITY = "인성"


class ValidStatus(str, Enum):
    VALID = "유효"
    INVALID = "무효"


class SessionStatus(str, Enum):
    IN_PROGRESS = "진행 중"
    COMPLETED = "완료"
    ABORTED = "중단"


class Emotion(str, Enum):
    ANGRY = "angry"
    DISGUST = "disgust"
    FEAR = "fear"
    HAPPY = "happy"
    SAD = "sad"
    SURPRISE = "surprise"
    NEUTRAL = "neutral"


class JudgmentCode(str, Enum):
    RESOLVED_SYSTEM = "RESOLVED_SYSTEM"
    RESOLVED_APPLICANT = "RESOLVED_APPLICANT"
    RESOLVED_UNKNOWN = "RESOLVED_UNKNOWN"
    UNRESOLVED_SYSTEM = "UNRESOLVED_SYSTEM"
    UNRESOLVED_APPLICANT = "UNRESOLVED_APPLICANT"
    UNRESOLVED_UNKNOWN = "UNRESOLVED_UNKNOWN"


class DefectCause(str, Enum):
    SYSTEM = "시스템 측"
    APPLICANT = "지원자 측"
    UNKNOWN = "원인 판단 불가"


class FollowUpAction(str, Enum):
    REPRESENT_AND_RESUME = "질문 다시 제시 후 재개"
    CONTINUE_AS_IS = "기존 질문 그대로 진행"
    ABORT_AND_RETAKE = "중단 후 재시험"


class Speaker(str, Enum):
    APPLICANT = "지원자"
    CHATBOT = "챗봇"


class PointType(str, Enum):
    STRENGTH = "강점"
    NEEDS_CHECK = "확인 필요"


class JobType(str, Enum):
    COMPANY_DOC_EMBED = "회사 문서 임베딩"
    DOC_REPORT = "서류 보고서"
    INTERVIEW_QUESTIONS = "면접 질문 생성"
    EXPRESSION_REPROCESS = "표정 분석 재처리"
    INTERVIEW_REPORT = "면접 보고서"


class JobStatus(str, Enum):
    PENDING = "대기"
    RUNNING = "실행 중"
    DONE = "완료"
    FAILED = "실패"


class SourceType(str, Enum):
    FUNCTIONAL_TALENT = "기능적 인재상"
    NONFUNCTIONAL_TALENT = "비기능적 인재상"
    PROJECT_DOC = "프로젝트 문서"


class UploadStatus(str, Enum):
    DONE = "등록 완료"
