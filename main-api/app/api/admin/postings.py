from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin
from app.models.member import Member
from app.schemas.company_questions import CompanyQuestionsIn, CompanyQuestionsOut
from app.schemas.doc_criteria import DocCriteriaIn, DocCriteriaOut
from app.schemas.interview_criteria import InterviewCriteriaIn, InterviewCriteriaOut
from app.schemas.doc_items import DocItemsIn, DocItemsOut
from app.schemas.review import PublishOut, ReviewOut
from app.schemas.posting import DocumentOut, PostingCreated, PostingDetail, PostingInfoIn
from app.schemas.posting_list import DraftOut, PostingListItem, PostingStats
from app.services.posting_service import PostingService

router = APIRouter(prefix="/api/admin/postings", tags=["admin-postings"])


@router.post("", response_model=PostingCreated, status_code=201)
async def create_posting(admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """ADM-004 채용공고 임시 생성"""
    return {"posting_id": await PostingService(db).create_draft(admin)}


@router.get("", response_model=list[PostingListItem])
async def list_postings(admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """ADM-012 채용공고 목록 (본인이 등록한 공고)"""
    return await PostingService(db).list_postings(admin)


# 주소가 겹치지 않도록 '/{posting_id}'보다 먼저 둔다
@router.get("/draft", response_model=DraftOut | None)
async def get_draft(admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """ADM-011 이어서 작성할 임시 저장 공고 (없으면 null)"""
    return await PostingService(db).get_draft(admin)


@router.get("/{posting_id}", response_model=PostingDetail)
async def get_posting(
    posting_id: int, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """ADM-013 채용공고 조회"""
    return await PostingService(db).get_detail(admin, posting_id)


@router.put("/{posting_id}/info", response_model=PostingDetail)
async def save_info(
    posting_id: int,
    req: PostingInfoIn,
    validate: bool = True,
    admin: Member = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """ADM-004 공고 정보 저장. 임시 저장은 validate=false"""
    return await PostingService(db).save_info(admin, posting_id, req, validate)


@router.post("/{posting_id}/documents", response_model=DocumentOut, status_code=201)
async def add_document(
    posting_id: int,
    file: UploadFile,
    admin: Member = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """ADM-005 프로젝트 문서(PDF) 등록"""
    return await PostingService(db).add_document(admin, posting_id, file)


@router.delete("/{posting_id}/documents/{document_id}", status_code=204)
async def delete_document(
    posting_id: int,
    document_id: int,
    admin: Member = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """ADM-015 프로젝트 문서 삭제"""
    await PostingService(db).delete_document(admin, posting_id, document_id)


@router.get("/{posting_id}/doc-items", response_model=DocItemsOut)
async def get_doc_items(
    posting_id: int, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """ADM-006 서류 작성 문항 조회"""
    return await PostingService(db).get_doc_items(admin, posting_id)


@router.put("/{posting_id}/doc-items", response_model=DocItemsOut)
async def save_doc_items(
    posting_id: int,
    req: DocItemsIn,
    validate: bool = True,
    admin: Member = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """ADM-006 서류 작성 문항 저장. 임시 저장은 validate=false"""
    return await PostingService(db).save_doc_items(admin, posting_id, req, validate)


@router.get("/{posting_id}/doc-criteria", response_model=DocCriteriaOut)
async def get_doc_criteria(
    posting_id: int, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """ADM-007 서류 평가기준 조회"""
    return await PostingService(db).get_doc_criteria(admin, posting_id)


@router.put("/{posting_id}/doc-criteria", response_model=DocCriteriaOut)
async def save_doc_criteria(
    posting_id: int,
    req: DocCriteriaIn,
    validate: bool = True,
    admin: Member = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """ADM-007 서류 평가기준 저장. 임시 저장은 validate=false"""
    return await PostingService(db).save_doc_criteria(admin, posting_id, req, validate)

@router.get("/{posting_id}/interview-criteria", response_model=InterviewCriteriaOut)
async def get_interview_criteria(
    posting_id: int, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """ADM-008 면접 평가기준 조회"""
    return await PostingService(db).get_interview_criteria(admin, posting_id)


@router.put("/{posting_id}/interview-criteria", response_model=InterviewCriteriaOut)
async def save_interview_criteria(
    posting_id: int,
    req: InterviewCriteriaIn,
    validate: bool = True,
    admin: Member = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """ADM-008 면접 평가기준 저장. 임시 저장은 validate=false"""
    return await PostingService(db).save_interview_criteria(admin, posting_id, req, validate)

@router.get("/{posting_id}/company-questions", response_model=CompanyQuestionsOut)
async def get_company_questions(
    posting_id: int, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """ADM-009 기업 질문 조회"""
    return await PostingService(db).get_company_questions(admin, posting_id)


@router.put("/{posting_id}/company-questions", response_model=CompanyQuestionsOut)
async def save_company_questions(
    posting_id: int,
    req: CompanyQuestionsIn,
    validate: bool = True,
    admin: Member = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """ADM-009 기업 질문과 AI 질문 비율 저장. 임시 저장은 validate=false"""
    return await PostingService(db).save_company_questions(admin, posting_id, req, validate)

@router.get("/{posting_id}/review", response_model=ReviewOut)
async def get_review(
    posting_id: int, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """ADM-010 작성 내용 최종 검토"""
    return await PostingService(db).get_review(admin, posting_id)


@router.post("/{posting_id}/publish", response_model=PublishOut)
async def publish_posting(
    posting_id: int, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """ADM-010 채용공고 등록"""
    return await PostingService(db).publish(admin, posting_id)


@router.get("/{posting_id}/documents/{document_id}/file")
async def get_document_file(
    posting_id: int,
    document_id: int,
    admin: Member = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """ADM-010, ADM-036 프로젝트 문서(PDF) 보기. 내려받지 않고 브라우저에서 바로 연다."""
    path, file_name = await PostingService(db).get_document_file(admin, posting_id, document_id)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=file_name,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff"},
    )

@router.delete("/{posting_id}", status_code=204)
async def delete_posting(
    posting_id: int, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """ADM-020 채용공고 삭제 ('모집 전' 공고만)"""
    await PostingService(db).delete_posting(admin, posting_id)

@router.get("/{posting_id}/stats", response_model=PostingStats)
async def get_stats(
    posting_id: int, admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """ADM-013 전형별 지원자 수 (제출, 면접 대상, 응시 완료)"""
    return await PostingService(db).get_stats(admin, posting_id)
