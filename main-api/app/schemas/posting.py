from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import EmploymentType


class PostingInfoIn(BaseModel):
    """화면 04 공고 정보. 임시 저장 때는 비어 있어도 되므로 모두 선택 값이다."""

    position_name: str | None = Field(default=None, max_length=255)
    job_category: str | None = Field(default=None, max_length=255)
    employment_type: EmploymentType | None = None
    job_description: str | None = None
    doc_start_at: AwareDatetime | None = None
    doc_end_at: AwareDatetime | None = None
    doc_result_at: AwareDatetime | None = None
    interview_start_at: AwareDatetime | None = None
    interview_end_at: AwareDatetime | None = None
    interview_result_at: AwareDatetime | None = None
    functional_talent: str | None = None
    nonfunctional_talent: str | None = None

    @field_validator("position_name", "job_category", "job_description", "functional_talent", "nonfunctional_talent")
    @classmethod
    def blank_to_none(cls, v: str | None) -> str | None:
        v = v.strip() if v else v
        return v or None


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: int
    file_name: str
    file_size: int | None
    upload_status: str | None


class PostingDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    posting_id: int
    write_status: str
    progress_status: str | None
    position_name: str | None
    job_category: str | None
    employment_type: str | None
    job_description: str | None
    doc_start_at: datetime | None
    doc_end_at: datetime | None
    doc_result_at: datetime | None
    interview_start_at: datetime | None
    interview_end_at: datetime | None
    interview_result_at: datetime | None
    functional_talent: str | None
    nonfunctional_talent: str | None
    documents: list[DocumentOut]


class PostingCreated(BaseModel):
    posting_id: int
