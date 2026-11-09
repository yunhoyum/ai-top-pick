from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import StageResult, StageType
from app.models.application import (
    ApplicantProject,
    ApplicantSkill,
    Application,
    ApplicationStage,
    Career,
    Education,
    EssayAnswer,
    Portfolio,
    SkillCase,
)
from app.models.member import Member
from app.models.posting import BasicItem, EssayTopic, PostingBasicItem, RequiredSkill, Skill


class ApplicationRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- 공고가 정한 구성 ----------
    async def item_names(self, posting_id: int) -> set[str]:
        rows = await self.db.scalars(
            select(BasicItem.item_name)
            .join(PostingBasicItem, PostingBasicItem.item_id == BasicItem.item_id)
            .where(PostingBasicItem.posting_id == posting_id)
        )
        return set(rows)

    async def required_skills(self, posting_id: int) -> list[tuple[int, str, int | None]]:
        """(기술ID, 기술명, 탈락 기준 점수). 공고 문항 화면과 같은 순서"""
        rows = await self.db.execute(
            select(Skill.skill_id, Skill.skill_name, RequiredSkill.cutoff_score)
            .join(Skill, Skill.skill_id == RequiredSkill.skill_id)
            .where(RequiredSkill.posting_id == posting_id)
            .order_by(RequiredSkill.skill_id)
        )
        return [(i, n, c) for i, n, c in rows]

    async def topics(self, posting_id: int) -> list[EssayTopic]:
        rows = await self.db.scalars(
            select(EssayTopic).where(EssayTopic.posting_id == posting_id).order_by(EssayTopic.seq)
        )
        return list(rows)

    # ---------- 지원서 ----------
    async def get(self, posting_id: int, applicant_id: int) -> Application | None:
        return await self.db.scalar(
            select(Application).where(
                Application.posting_id == posting_id, Application.applicant_id == applicant_id
            )
        )

    async def create(self, posting_id: int, member: Member) -> Application:
        application = Application(
            posting_id=posting_id,
            applicant_id=member.member_id,
            applicant_name=member.name,
            applicant_email=member.email,
        )
        self.db.add(application)
        await self.db.flush()
        return application

    async def educations(self, application_id: int) -> list[Education]:
        rows = await self.db.scalars(
            select(Education).where(Education.application_id == application_id).order_by(Education.education_id)
        )
        return list(rows)

    async def careers(self, application_id: int) -> list[Career]:
        rows = await self.db.scalars(
            select(Career).where(Career.application_id == application_id).order_by(Career.career_id)
        )
        return list(rows)

    async def projects(self, application_id: int) -> list[ApplicantProject]:
        rows = await self.db.scalars(
            select(ApplicantProject)
            .where(ApplicantProject.application_id == application_id)
            .order_by(ApplicantProject.project_id)
        )
        return list(rows)

    async def replace_resume(
        self,
        application_id: int,
        educations: list[Education],
        careers: list[Career],
        projects: list[ApplicantProject],
    ) -> None:
        """이력서의 학력, 경력, 프로젝트를 모두 지우고 다시 넣는다. 호출한 쪽이 commit한다."""
        for model in (Education, Career, ApplicantProject):
            await self.db.execute(delete(model).where(model.application_id == application_id))
        self.db.add_all([*educations, *careers, *projects])
        await self.db.flush()

    async def skill_scores(self, application_id: int) -> list[tuple[int, str, int | None]]:
        rows = await self.db.execute(
            select(Skill.skill_id, Skill.skill_name, ApplicantSkill.self_score)
            .join(Skill, Skill.skill_id == ApplicantSkill.skill_id)
            .where(ApplicantSkill.application_id == application_id)
            .order_by(Skill.skill_id)
        )
        return [(i, n, s) for i, n, s in rows]

    async def cases(self, application_id: int) -> list[tuple[int | None, str | None, str | None]]:
        """(기술ID, 기술명, 내용). 입력한 순서"""
        rows = await self.db.execute(
            select(SkillCase.skill_id, Skill.skill_name, SkillCase.content)
            .outerjoin(Skill, Skill.skill_id == SkillCase.skill_id)
            .where(SkillCase.application_id == application_id)
            .order_by(SkillCase.seq, SkillCase.skill_case_id)
        )
        return [(i, n, c) for i, n, c in rows]

    async def replace_skills(
        self,
        application_id: int,
        scores: list[tuple[int, int | None]],
        cases: list[tuple[int | None, str | None]],
    ) -> None:
        """기술 점수와 기술 적용 사례를 모두 지우고 다시 넣는다. 호출한 쪽이 commit한다."""
        await self.db.execute(delete(ApplicantSkill).where(ApplicantSkill.application_id == application_id))
        await self.db.execute(delete(SkillCase).where(SkillCase.application_id == application_id))
        self.db.add_all(
            ApplicantSkill(application_id=application_id, skill_id=skill_id, self_score=score)
            for skill_id, score in scores
        )
        self.db.add_all(
            SkillCase(application_id=application_id, skill_id=skill_id, seq=seq, content=content)
            for seq, (skill_id, content) in enumerate(cases, start=1)
        )
        await self.db.flush()

    async def essays(self, application_id: int) -> dict[int, str | None]:
        rows = await self.db.execute(
            select(EssayAnswer.topic_id, EssayAnswer.content).where(EssayAnswer.application_id == application_id)
        )
        return {topic_id: content for topic_id, content in rows}

    async def replace_essays(self, application_id: int, essays: list[tuple[int, str | None]]) -> None:
        await self.db.execute(delete(EssayAnswer).where(EssayAnswer.application_id == application_id))
        self.db.add_all(
            EssayAnswer(application_id=application_id, topic_id=topic_id, content=content)
            for topic_id, content in essays
        )
        await self.db.flush()

    async def portfolio(self, application_id: int) -> Portfolio | None:
        return await self.db.scalar(select(Portfolio).where(Portfolio.application_id == application_id))

    async def set_portfolio(self, application_id: int, name: str, size: int, path: str) -> Portfolio:
        portfolio = await self.portfolio(application_id)
        if portfolio is None:
            portfolio = Portfolio(application_id=application_id, file_name=name, file_size=size, file_path=path)
            self.db.add(portfolio)
        else:
            portfolio.file_name, portfolio.file_size, portfolio.file_path = name, size, path
        await self.db.flush()
        return portfolio

    async def delete_portfolio(self, portfolio: Portfolio) -> None:
        await self.db.delete(portfolio)
        await self.db.flush()

    async def record_skill_shortfall(self, application_id: int) -> None:
        """서류 제출 때 필수 기술 기준에 걸린 지원서는 서류 전형 결과를 '필수 기술 미달'로 남긴다 (ADM-003)."""
        self.db.add(
            ApplicationStage(
                application_id=application_id,
                stage_type=StageType.DOCUMENT.value,
                result=StageResult.SKILL_SHORTFALL.value,
            )
        )
        await self.db.flush()
