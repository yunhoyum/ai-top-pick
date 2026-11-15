"""Deepgram 실시간 음성 인식 중계 (코드베이스 1. main-api 8장 DeepgramRelay, 아키텍처 7-6·7.1, SYS-004).

답변 시간 동안만 연다. 브라우저가 보낸 음성 조각(webm/opus)을 그대로 보내고, 인식 결과를 받는다.
- 중간 결과(is_final 거짓)는 실시간 자막에만 쓴다.
- 확정 결과(is_final 참)의 단어를 모아 답변 원문과 단어별 시각을 만든다. 시각은 스트림 시작 기준 초다.
키는 main-api만 가진다. 브라우저에 보내지 않는다.
"""

import asyncio
import json
import logging
from typing import Awaitable, Callable
from urllib.parse import urlencode

import websockets

from app.core.config import get_settings

log = logging.getLogger(__name__)

# (글, 확정 여부) → 자막·무발화 판단에 쓴다
OnResult = Callable[[str, bool], Awaitable[None]]


class DeepgramRelay:
    def __init__(self, on_result: OnResult):
        self.on_result = on_result
        self.words: list[dict] = []  # 확정 단어 {word, start, end}
        self.texts: list[str] = []  # 확정 글 (원문)
        self._ws = None
        self._reader: asyncio.Task | None = None

    async def connect(self) -> None:
        s = get_settings()
        params = {
            "model": s.DEEPGRAM_MODEL, "language": "ko", "punctuate": "true",
            "interim_results": "true", "filler_words": "true",
        }
        self._ws = await websockets.connect(
            f"{s.DEEPGRAM_URL}?{urlencode(params)}",
            additional_headers={"Authorization": f"Token {s.DEEPGRAM_API_KEY}"},
        )
        self._reader = asyncio.create_task(self._read())

    async def send_audio(self, chunk: bytes) -> None:
        if self._ws is not None:
            await self._ws.send(chunk)

    async def _read(self) -> None:
        async for raw in self._ws:
            msg = json.loads(raw)
            if msg.get("type") != "Results":
                continue
            alt = msg["channel"]["alternatives"][0]
            text = alt.get("transcript", "").strip()
            if msg.get("is_final") and text:
                self.texts.append(text)
                # 문장부호가 붙은 낱말(punctuated_word)로 둔다. 구간을 나눌 때 문장 끝을 본다 (ai-service split_segments)
                self.words += [
                    {"word": w.get("punctuated_word") or w["word"], "start": w["start"], "end": w["end"]}
                    for w in alt.get("words", [])
                ]
            if text:
                await self.on_result(text, bool(msg.get("is_final")))

    async def close(self, timeout: float = 10.0) -> tuple[str, list[dict]]:
        """남은 음성을 마저 인식하게 하고 닫는다. (답변 원문, 단어 목록)을 돌려준다."""
        if self._ws is not None:
            try:
                await self._ws.send(json.dumps({"type": "CloseStream"}))
                await asyncio.wait_for(self._reader, timeout)
            except websockets.ConnectionClosedOK:
                pass  # Deepgram이 먼저 정상 종료했다 (결과는 이미 다 받았다)
            except Exception as e:
                log.warning("Deepgram 연결을 닫는 중 오류: %s", e)
            finally:
                await self._ws.close()
        return " ".join(self.texts), self.words
