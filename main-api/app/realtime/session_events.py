"""응시별 최근 이벤트 (코드베이스 1. main-api 8장 SessionEventBuffer, 화면 26 시스템 로그).

연결·재연결·끊김, 질문 제시, 생각·답변 시간, 음성 인식·영상 업로드 실패, 오류를 시각과 함께 남긴다.
문의가 열리면 진행 중인 질문이 시작된 때부터의 이벤트를 system_log로 옮기고 LLM에 보낸다 (SYS-003).
답변 평가 중에 받아 둔 문의는 이전 질문이 시작된 때부터 보낸다 (AI Agent 설계서 4.5).
main-api는 uvicorn 워커 1개라 메모리에 둔다 (코드베이스 3장). 재연결해도 같은 응시의 이벤트가 이어진다.
"""

from collections import defaultdict, deque
from datetime import datetime, timezone

MAX_EVENTS = 200  # 응시 하나에 남길 최근 이벤트 수 (제안)

_events: dict[int, deque] = defaultdict(lambda: deque(maxlen=MAX_EVENTS))
_question_starts: dict[int, list[int]] = defaultdict(list)  # 질문이 시작된 이벤트 순번
_counter: dict[int, int] = defaultdict(int)


def record(session_id: int, content: str) -> None:
    _counter[session_id] += 1
    _events[session_id].append((_counter[session_id], datetime.now(timezone.utc).isoformat(), content))


def question_started(session_id: int, content: str) -> None:
    """질문 제시를 남기고 그 순번을 질문 시작으로 둔다."""
    record(session_id, content)
    _question_starts[session_id].append(_counter[session_id])


def since_question(session_id: int, previous: bool = False) -> list[dict]:
    """진행 중인 질문(previous면 그 앞 질문)이 시작된 때부터의 이벤트 [{logged_at, content}]."""
    starts = _question_starts[session_id]
    idx = -2 if previous else -1
    start = starts[idx] if len(starts) >= -idx else 0
    return [{"logged_at": at, "content": c} for n, at, c in _events[session_id] if n >= start]
