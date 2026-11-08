from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.posting import EvalCriteria, PostingEvalRatio


class EvalRatioRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_criteria(self, stage_type: str) -> list[EvalCriteria]:
        result = await self.db.scalars(
            select(EvalCriteria)
            .where(EvalCriteria.stage_type == stage_type)
            .order_by(EvalCriteria.criteria_id)
        )
        return list(result)

    async def ratios(self, posting_id: int, criteria_ids: list[int]) -> dict[int, int | None]:
        rows = await self.db.execute(
            select(PostingEvalRatio.criteria_id, PostingEvalRatio.ratio).where(
                PostingEvalRatio.posting_id == posting_id,
                PostingEvalRatio.criteria_id.in_(criteria_ids),
            )
        )
        return {criteria_id: ratio for criteria_id, ratio in rows}

    async def replace(self, posting_id: int, criteria_ids: list[int], ratios: dict[int, int]) -> None:
        """지정한 평가 항목의 비율만 지우고 다시 넣는다. 서류와 면접이 한 테이블을 쓰므로
        다른 전형의 항목은 건드리지 않는다. 호출한 쪽이 commit한다."""
        await self.db.execute(
            delete(PostingEvalRatio).where(
                PostingEvalRatio.posting_id == posting_id,
                PostingEvalRatio.criteria_id.in_(criteria_ids),
            )
        )
        self.db.add_all(
            PostingEvalRatio(posting_id=posting_id, criteria_id=cid, ratio=ratio)
            for cid, ratio in ratios.items()
        )
        await self.db.flush()
