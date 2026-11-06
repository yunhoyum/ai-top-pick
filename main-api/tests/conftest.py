import asyncio
import sys

import pytest
from fastapi.testclient import TestClient

# Windows 로컬 실행용: psycopg 비동기 모드는 Proactor 이벤트 루프를 쓰지 못한다 (Docker/Linux에는 해당 없음)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture
def client():
    # DATABASE_URL이 마이그레이션이 끝난 DB를 가리켜야 한다
    from app.main import app

    with TestClient(app) as c:
        yield c
