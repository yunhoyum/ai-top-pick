from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.posting import CompanyQuestion


class CompanyQuestionRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_contents(self, posting_id: int) -> list[str]:
        rows = await self.db.scalars(
            select(CompanyQuestion.content)
            .where(CompanyQuestion.posting_id == posting_id)
            .order_by(CompanyQuestion.seq, CompanyQuestion.company_question_id)
        )
        return list(rows)

    async def replace_all(self, posting_id: int, contents: list[str]) -> None:
        """공고의 기업 질문을 모두 지우고 목록 순서대로 다시 넣는다. 호출한 쪽이 commit한다."""
        await self.db.execute(delete(CompanyQuestion).where(CompanyQuestion.posting_id == posting_id))
        self.db.add_all(
            CompanyQuestion(posting_id=posting_id, seq=seq, content=content)
            for seq, content in enumerate(contents, start=1)
        )
        await self.db.flush()
