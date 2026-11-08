from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.posting import BasicItem, EssayTopic, PostingBasicItem, RequiredSkill, Skill


class DocItemRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_basic_items(self) -> list[BasicItem]:
        # 필수 문항(인적사항, 기술 적용 사례)을 앞에 두고 나머지는 번호 순서로 보여 준다
        result = await self.db.scalars(
            select(BasicItem).order_by(BasicItem.is_required.desc(), BasicItem.item_id)
        )
        return list(result)

    async def selected_item_ids(self, posting_id: int) -> set[int]:
        rows = await self.db.scalars(
            select(PostingBasicItem.item_id).where(PostingBasicItem.posting_id == posting_id)
        )
        return set(rows)

    async def list_skills(self, posting_id: int) -> list[tuple[str, int | None]]:
        rows = await self.db.execute(
            select(Skill.skill_name, RequiredSkill.cutoff_score)
            .join(Skill, Skill.skill_id == RequiredSkill.skill_id)
            .where(RequiredSkill.posting_id == posting_id)
            .order_by(RequiredSkill.skill_id)
        )
        return [(name, cutoff) for name, cutoff in rows]

    async def list_topics(self, posting_id: int) -> list[str]:
        rows = await self.db.scalars(
            select(EssayTopic.topic_name)
            .where(EssayTopic.posting_id == posting_id)
            .order_by(EssayTopic.seq)
        )
        return list(rows)

    async def replace_all(
        self,
        posting_id: int,
        item_ids: list[int],
        skills: list[tuple[str, int | None]],
        topics: list[str],
    ) -> None:
        """공고의 기본 문항, 필수 기술, 자소서 주제를 모두 지우고 다시 넣는다. 호출한 쪽이 commit한다."""
        await self.db.execute(delete(PostingBasicItem).where(PostingBasicItem.posting_id == posting_id))
        await self.db.execute(delete(RequiredSkill).where(RequiredSkill.posting_id == posting_id))
        await self.db.execute(delete(EssayTopic).where(EssayTopic.posting_id == posting_id))

        self.db.add_all(PostingBasicItem(posting_id=posting_id, item_id=i) for i in item_ids)
        for name, cutoff in skills:
            skill_id = await self._get_or_create_skill(name)
            self.db.add(RequiredSkill(posting_id=posting_id, skill_id=skill_id, cutoff_score=cutoff))
        self.db.add_all(
            EssayTopic(posting_id=posting_id, seq=seq, topic_name=name)
            for seq, name in enumerate(topics, start=1)
        )
        await self.db.flush()

    async def _get_or_create_skill(self, name: str) -> int:
        """대소문자를 구분하지 않고 같은 이름의 기술을 재사용한다. 동시에 만들어도 한 행만 남는다."""
        found = await self._find_skill(name)
        if found is not None:
            return found
        await self.db.execute(insert(Skill).values(skill_name=name).on_conflict_do_nothing())
        return await self._find_skill(name)  # type: ignore[return-value]

    async def _find_skill(self, name: str) -> int | None:
        return await self.db.scalar(
            select(Skill.skill_id).where(func.lower(Skill.skill_name) == name.lower())
        )
