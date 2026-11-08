from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ProgressStatus
from app.models.posting import CompanyQuestion, JobPosting, PostingDocument


class PostingRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, admin_id: int) -> JobPosting:
        posting = JobPosting(admin_id=admin_id, progress_status=ProgressStatus.BEFORE_RECRUIT.value)
        self.db.add(posting)
        await self.db.flush()
        return posting

    async def get_owned(self, admin_id: int, posting_id: int) -> JobPosting | None:
        """본인이 작성한 공고만 조회한다."""
        return await self.db.scalar(
            select(JobPosting).where(
                JobPosting.posting_id == posting_id, JobPosting.admin_id == admin_id
            )
        )

    async def count_company_questions(self, posting_id: int) -> int:
        return await self.db.scalar(
            select(func.count()).select_from(CompanyQuestion).where(CompanyQuestion.posting_id == posting_id)
        )

    async def list_documents(self, posting_id: int) -> list[PostingDocument]:
        result = await self.db.scalars(
            select(PostingDocument)
            .where(PostingDocument.posting_id == posting_id)
            .order_by(PostingDocument.document_id)
        )
        return list(result)

    async def add_document(self, document: PostingDocument) -> PostingDocument:
        self.db.add(document)
        await self.db.flush()
        return document

    async def get_document(self, posting_id: int, document_id: int) -> PostingDocument | None:
        return await self.db.scalar(
            select(PostingDocument).where(
                PostingDocument.posting_id == posting_id,
                PostingDocument.document_id == document_id,
            )
        )

    async def delete_document(self, document: PostingDocument) -> None:
        await self.db.delete(document)
        await self.db.flush()
