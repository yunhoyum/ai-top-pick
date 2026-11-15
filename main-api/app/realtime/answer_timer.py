"""생각 시간·답변 시간 (코드베이스 1. main-api 8장 AnswerTimer, APP-016, SYS-011).

브라우저 메시지는 WebSocket을 읽는 쪽이 events 큐에 넣는다. 타이머는 큐를 보며 시간을 센다.
- 생각 시간: 질문 음성이 끝난 시점부터 센다. 이 동안 '답변 완료' 버튼은 받지 않는다.
- 답변 시간: '답변 완료' 버튼(button), 첫 단어 이후 10초 무발화(silence), 답변 시간 종료(timeout) 중 먼저 온 것.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Literal

EndReason = Literal["button", "silence", "timeout", "disconnect"]
DISCONNECTED = {"type": "__disconnected__"}  # 읽는 쪽이 연결이 끊기면 넣는다
SPEECH = {"type": "__speech__"}  # Deepgram이 말소리를 인식할 때마다 넣는다 (무발화 판단)


@dataclass
class AnswerTimer:
    events: asyncio.Queue
    question_id: int

    async def _next(self, deadline: float) -> dict | None:
        """deadline까지 다음 메시지. 시간이 다 되면 None."""
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            return await asyncio.wait_for(self.events.get(), remaining)
        except asyncio.TimeoutError:
            return None

    async def wait_audio_end(self, max_sec: float) -> bool:
        """질문 음성 재생이 끝났다는 메시지를 기다린다. 브라우저가 알려 주지 않아도 max_sec 뒤에는 넘어간다.
        연결이 끊기면 거짓."""
        deadline = time.monotonic() + max_sec
        while (msg := await self._next(deadline)) is not None:
            if msg is DISCONNECTED:
                return False
            if msg.get("type") == "question_audio_ended" and msg.get("question_id") == self.question_id:
                return True
        return True

    async def start_think(self, sec: float) -> bool:
        """생각 시간이 끝날 때까지 기다린다. 이 동안 온 '답변 완료'는 버린다. 연결이 끊기면 거짓."""
        deadline = time.monotonic() + sec
        while (msg := await self._next(deadline)) is not None:
            if msg is DISCONNECTED:
                return False
        return True

    async def start_answer(self, sec: float, silence_sec: float | None = None) -> EndReason:
        """답변 시간을 센다. 이때부터 '답변 완료' 버튼을 받는다.
        silence_sec를 주면 첫 단어 이후 그만큼 말이 없을 때 끝낸다(silence). 첫 단어가 없으면 버튼과 시간 종료로만 끝난다.
        말소리는 Deepgram 결과가 올 때 SPEECH 메시지로 들어온다 (on_word)."""
        deadline = time.monotonic() + sec
        last_speech: float | None = None
        while True:
            silence_at = last_speech + silence_sec if (last_speech is not None and silence_sec) else None
            msg = await self._next(min(deadline, silence_at) if silence_at else deadline)
            if msg is None:
                return "silence" if silence_at is not None and silence_at < deadline and time.monotonic() >= silence_at else "timeout"
            if msg is DISCONNECTED:
                return "disconnect"
            if msg.get("type") == SPEECH["type"]:
                last_speech = time.monotonic()
            elif msg.get("type") == "answer_done" and msg.get("question_id") == self.question_id:
                return "button"
