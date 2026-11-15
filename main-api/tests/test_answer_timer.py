"""답변 타이머 테스트 (APP-016). 시간은 가짜로 바꿔 정해 둔 순서대로 흐르게 한다."""

import asyncio

from app.realtime import answer_timer
from app.realtime.answer_timer import SPEECH, AnswerTimer


def test_silence_is_reported_even_if_the_wait_wakes_slightly_early(monkeypatch):
    """대기가 무발화 시각보다 조금 일찍 깨어나도 종료 이유는 silence다 (e2e 세션 241에서 timeout으로 나왔다)."""
    monkeypatch.setattr(answer_timer.time, "monotonic", lambda: 100.0)  # 시계가 멈춘 것처럼: 깨어난 시각 < 무발화 시각
    replies = iter([SPEECH, None])

    async def fake_next(self, deadline):
        return next(replies)

    monkeypatch.setattr(AnswerTimer, "_next", fake_next)
    timer = AnswerTimer(asyncio.Queue(), question_id=1)
    assert asyncio.run(timer.start_answer(40, silence_sec=10)) == "silence"


def test_timeout_without_speech(monkeypatch):
    monkeypatch.setattr(AnswerTimer, "_next", lambda self, deadline: asyncio.sleep(0))  # 곧바로 None
    timer = AnswerTimer(asyncio.Queue(), question_id=1)
    assert asyncio.run(timer.start_answer(40, silence_sec=10)) == "timeout"
