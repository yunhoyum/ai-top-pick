"""DB 연결. main-api는 비동기 세션, Celery worker는 동기 세션을 쓴다."""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

_url = get_settings().sqlalchemy_url

# create_*engine 은 만들 때 접속하지 않는다. 첫 쿼리 때 접속한다
# pool_pre_ping: 끊어진 연결을 쓰기 전에 걸러낸다 (DB 재시작 대비)
async_engine = create_async_engine(_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)

sync_engine = create_engine(_url, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)
