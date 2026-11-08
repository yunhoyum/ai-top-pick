from pydantic import BaseModel

from app.schemas.company_questions import CompanyQuestionsOut
from app.schemas.doc_criteria import DocCriteriaOut
from app.schemas.doc_items import DocItemsOut
from app.schemas.interview_criteria import InterviewCriteriaOut
from app.schemas.posting import PostingDetail


class ReviewOut(BaseModel):
    """화면 09 작성 내용 최종 검토. 모든 단계의 저장된 내용을 한 번에 돌려준다."""

    posting: PostingDetail
    doc_items: DocItemsOut
    doc_criteria: DocCriteriaOut
    interview_criteria: InterviewCriteriaOut
    company_questions: CompanyQuestionsOut
    # 아직 완료하지 못한 단계. 화면 주소의 단계 이름과 같다 (info, doc-items, doc-criteria, interview-criteria, company-questions)
    incomplete_steps: list[str]


class PublishOut(BaseModel):
    posting_id: int
    write_status: str
