from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import (
    ApplicationWriteStatus,
    PostingWriteStatus,
    ProgressStatus,
    SessionStatus,
    StageResult,
    StageType,
)
from app.models.application import Application, ApplicationStage
from app.models.inquiry import Inquiry, JudgmentType
from app.models.interview import InterviewSession
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

    async def get_registered(self, posting_id: int) -> JobPosting | None:
        """등록을 마친 공고 한 건 (임시 저장 공고는 없는 것으로 본다)"""
        return await self.db.scalar(
            select(JobPosting).where(
                JobPosting.posting_id == posting_id,
                JobPosting.write_status == PostingWriteStatus.COMPLETE.value,
            )
        )

    async def list_public(self) -> list[JobPosting]:
        """등록을 마친 모든 공고. 최근에 만든 공고가 먼저 나온다."""
        rows = await self.db.scalars(
            select(JobPosting)
            .where(JobPosting.write_status == PostingWriteStatus.COMPLETE.value)
            .order_by(JobPosting.posting_id.desc())
        )
        return list(rows)

    async def stats(self, posting_id: int) -> tuple[int, int, int, int, int]:
        """전형별 지원자 수와 오류 수: (제출, 면접 대상, 면접 응시 완료, 필수 기술 미달 탈락, AI 미처리 오류)"""
        submitted = await self.db.scalar(
            select(func.count())
            .select_from(Application)
            .where(
                Application.posting_id == posting_id,
                Application.write_status == ApplicationWriteStatus.SUBMITTED.value,
            )
        )
        target = await self.db.scalar(
            select(func.count())
            .select_from(ApplicationStage)
            .join(Application, Application.application_id == ApplicationStage.application_id)
            .where(
                Application.posting_id == posting_id,
                ApplicationStage.stage_type == StageType.DOCUMENT.value,
                ApplicationStage.result == StageResult.PASS.value,
            )
        )
        done = await self.db.scalar(
            select(func.count(func.distinct(InterviewSession.application_id)))
            .select_from(InterviewSession)
            .join(Application, Application.application_id == InterviewSession.application_id)
            .where(
                Application.posting_id == posting_id,
                InterviewSession.status == SessionStatus.COMPLETED.value,
            )
        )
        shortfall = await self.db.scalar(
            select(func.count())
            .select_from(ApplicationStage)
            .join(Application, Application.application_id == ApplicationStage.application_id)
            .where(
                Application.posting_id == posting_id,
                ApplicationStage.stage_type == StageType.DOCUMENT.value,
                ApplicationStage.result == StageResult.SKILL_SHORTFALL.value,
            )
        )
        # 문의 중 판단 결과가 'AI가 문의 중에 해결하지 못함'(미해결)인 건
        unhandled = await self.db.scalar(
            select(func.count())
            .select_from(Inquiry)
            .join(InterviewSession, InterviewSession.session_id == Inquiry.session_id)
            .join(Application, Application.application_id == InterviewSession.application_id)
            .join(JudgmentType, JudgmentType.judgment_code == Inquiry.judgment_code)
            .where(Application.posting_id == posting_id, JudgmentType.ai_handled.is_(False))
        )
        return submitted, target, done, shortfall, unhandled

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
