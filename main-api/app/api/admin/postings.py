from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin
from app.models.member import Member
from app.schemas.doc_items import DocItemsIn, DocItemsOut
from app.schemas.posting import DocumentOut, PostingCreated, PostingDetail, PostingInfoIn
from app.services.posting_service import PostingService

router = APIRouter(prefix="/api/admin/postings", tags=["admin-postings"])


@router.post("", response_model=PostingCreated, status_code=201)
async def create_posting(admin: Member = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """ADM-004 채용공고 임시 생성"""
    return {"posting_id": await PostingService(db).create_draft(admin)}


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
