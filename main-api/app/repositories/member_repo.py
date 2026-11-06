from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.member import Company, Member


class MemberRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, member_id: int) -> Member | None:
        return await self.db.get(Member, member_id)

    async def get_by_email(self, email: str) -> Member | None:
        return await self.db.scalar(select(Member).where(Member.email == email))

    async def get_or_create_company(self, company_name: str) -> Company:
        company = await self.db.scalar(
            select(Company).where(Company.company_name == company_name)
        )
        if company is None:
            company = Company(company_name=company_name)
            self.db.add(company)
            await self.db.flush()
        return company

    async def create(self, member: Member) -> Member:
        self.db.add(member)
        await self.db.flush()
        return member
