from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ApplicationWriteStatus, PostingWriteStatus, ProgressStatus
from app.models.application import Application
from app.models.posting import (
    CompanyQuestion,
    EssayTopic,
    JobPosting,
    PostingBasicItem,
    PostingDocument,
    PostingEvalRatio,
    RequiredSkill,
)


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

    async def list_registered(self, admin_id: int) -> list[tuple[JobPosting, int]]:
        """본인이 등록을 마친 공고와 제출된 지원서 수. 최근에 만든 공고가 먼저 나온다."""
        rows = await self.db.execute(
            select(JobPosting, func.count(Application.application_id))
            .outerjoin(
                Application,
                and_(
                    Application.posting_id == JobPosting.posting_id,
                    Application.write_status == ApplicationWriteStatus.SUBMITTED.value,
                ),
            )
            .where(
                JobPosting.admin_id == admin_id,
                JobPosting.write_status == PostingWriteStatus.COMPLETE.value,
            )
            .group_by(JobPosting.posting_id)
            .order_by(JobPosting.posting_id.desc())
        )
        return [(posting, count) for posting, count in rows]

    async def latest_draft(self, admin_id: int) -> JobPosting | None:
        """본인이 가장 최근에 임시 저장한(등록하지 않은) 공고"""
        return await self.db.scalar(
            select(JobPosting)
            .where(
                JobPosting.admin_id == admin_id,
                JobPosting.write_status == PostingWriteStatus.DRAFT.value,
            )
            .order_by(JobPosting.posting_id.desc())
            .limit(1)
        )

    async def delete_posting(self, posting: JobPosting) -> None:
        """공고와 딸린 행을 모두 지운다. 하위 테이블에 ON DELETE CASCADE가 없어 직접 지운다."""
        posting_id = posting.posting_id
        for model in (
            PostingDocument,
            PostingBasicItem,
            PostingEvalRatio,
            RequiredSkill,
            EssayTopic,
            CompanyQuestion,
        ):
            await self.db.execute(delete(model).where(model.posting_id == posting_id))
        await self.db.delete(posting)
        await self.db.flush()

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
