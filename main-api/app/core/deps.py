from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal


async def get_db() -> AsyncIterator[AsyncSession]:
    """요청마다 DB 세션을 연다."""
    async with AsyncSessionLocal() as session:
        yield session
