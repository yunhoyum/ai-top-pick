"""답변 영상 업로드 완료를 기다린다 (코드베이스 1. main-api 8장 UploadRegistry, 아키텍처 7-7).

영상은 HTTP로 올라오고, 답변 처리는 WebSocket이 한다. 둘은 같은 main-api 프로세스(uvicorn 워커 1개)라서
메모리로 이어 준다 (코드베이스 3장). 업로드가 기다림보다 먼저 끝나도 놓치지 않게 결과를 남겨 둔다.
짧게 나눠 확인한다. 이벤트 루프가 달라도(테스트) 동작한다.
"""

import asyncio
import time

POLL_SEC = 0.1
_done: dict[tuple[int, int], str] = {}


def notify(session_id: int, question_id: int, path: str) -> None:
    _done[(session_id, question_id)] = path


async def wait(session_id: int, question_id: int, timeout: float) -> str | None:
    """업로드된 영상 경로. timeout 안에 오지 않으면 None."""
    key = (session_id, question_id)
    deadline = time.monotonic() + timeout
    while key not in _done and time.monotonic() < deadline:
        await asyncio.sleep(POLL_SEC)
    return _done.pop(key, None)


def forget(session_id: int, question_id: int) -> None:
    """같은 질문을 다시 받을 때(재접속) 이전 업로드 표시를 지운다."""
    _done.pop((session_id, question_id), None)
