from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.schemas.posting_list import PublicPostingDetail, PublicPostingItem
from app.services.posting_service import PostingService

router = APIRouter(prefix="/api/postings", tags=["postings"])


@router.get("", response_model=list[PublicPostingItem])
async def list_postings(db: AsyncSession = Depends(get_db)):
    """APP-003 채용공고 목록. 비로그인도 볼 수 있다."""
    return await PostingService(db).list_public()


@router.get("/{posting_id}", response_model=PublicPostingDetail)
async def get_posting(posting_id: int, db: AsyncSession = Depends(get_db)):
    """APP-004 채용공고 상세. 비로그인도 볼 수 있다."""
    return await PostingService(db).get_public(posting_id)
