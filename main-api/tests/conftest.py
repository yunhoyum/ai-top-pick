import asyncio
import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

# 업로드 테스트가 실제 저장소(STORAGE_ROOT)를 건드리지 않게 설정을 읽기 전에 임시 폴더로 돌린다
os.environ["STORAGE_ROOT"] = tempfile.mkdtemp(prefix="aitoppick-test-storage-")

# Windows 로컬 실행용: psycopg 비동기 모드는 Proactor 이벤트 루프를 쓰지 못한다 (Docker/Linux에는 해당 없음)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture
def client():
    # DATABASE_URL이 마이그레이션이 끝난 DB를 가리켜야 한다
    from app.main import app

    with TestClient(app) as c:
        yield c
