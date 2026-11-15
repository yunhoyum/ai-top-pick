"""LangGraph PostgreSQL 체크포인터 (ai-service 7장, 아키텍처 9.3).

면접 그래프의 State를 PC1 postgres에 저장한다. 서버가 재시작되거나 지원자가 재접속해도 상태가 남는다.
체크포인트 테이블은 앱이 처음 쓸 때 만든다 (setup). 업무 테이블에는 쓰지 않는다 (아키텍처 4.1-3).
"""

from functools import lru_cache

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import get_settings


@lru_cache
def get_checkpointer() -> PostgresSaver:
    # PostgresSaver가 요구하는 연결 설정 (langgraph-checkpoint-postgres 안내)
    pool = ConnectionPool(
        get_settings().DATABASE_URL,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=True,
    )
    saver = PostgresSaver(pool)
    saver.setup()
    return saver
