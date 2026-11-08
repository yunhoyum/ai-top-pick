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
