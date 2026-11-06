"""Windows 로컬 디버깅용 실행 스크립트. Docker에서는 쓰지 않는다.

psycopg 비동기 모드는 Windows 기본 이벤트 루프(Proactor)를 쓰지 못한다.
uvicorn이 루프를 만들기 전에 Selector 루프로 바꿔 둔다.
"""

import asyncio
import sys

import uvicorn

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8010, loop="none")
