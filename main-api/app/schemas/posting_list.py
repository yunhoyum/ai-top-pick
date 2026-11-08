from datetime import datetime

from pydantic import BaseModel


class PostingListItem(BaseModel):
    """화면 10 채용공고 목록의 한 줄"""

    posting_id: int
    position_name: str | None
    employment_type: str | None
    progress_status: str | None
    doc_start_at: datetime | None
    doc_end_at: datetime | None
    # 제출 완료된 지원서 수 (임시 저장한 지원서는 세지 않는다)
    applicant_count: int


class DraftOut(BaseModel):
    """이어서 작성할 수 있는 임시 저장 공고"""

    posting_id: int
    position_name: str | None
    # 이어서 작성할 때 열 단계: 아직 완료하지 못한 첫 단계. 모두 완료했으면 review
    resume_step: str


class PostingStats(BaseModel):
    """화면 11 전형 진행: 전형별 지원자 수 (ADM-013)"""

    # 제출 완료된 지원서 수
    submitted_count: int
    # 서류 전형에서 합격한 지원서 수 (면접 대상)
    interview_target_count: int
    # 면접을 끝까지 응시한(상태 '완료') 지원서 수
    interview_done_count: int
    # 서류 제출 때 필수 기술 기준에 걸려 바로 탈락한 지원서 수 (ADM-003)
    skill_shortfall_count: int
    # 면접 중 문의에서 AI가 처리하지 못한(미해결) 건수 (ADM-003)
    ai_unhandled_error_count: int
