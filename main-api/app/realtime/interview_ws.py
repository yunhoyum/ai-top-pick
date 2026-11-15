"""면접 WebSocket 처리 (코드베이스 1. main-api 8장 InterviewSocketHandler, 내부 API 규약 1장).

흐름:
  인증 → 응시 확인 → ai-service /start → [질문 + 음성 전송 → 음성 종료 → 생각 시간 → 답변 시간
  (브라우저 음성 → Deepgram → 자막) → '답변 완료'·무발화·시간 종료 → 영상 업로드 대기
  → ai-service /answer → 답변·STT 저장] 반복 → 종료(응시 '완료')
표정 재처리는 3단계, 문의는 5단계에서 넣는다.
연결이 끊기면 응시는 '진행 중'으로 둔다. 다시 연결하면 같은 체크포인트로 이어간다 (아키텍처 9.3).
"""

import asyncio
import base64
import json
import logging
from datetime import datetime, timedelta, timezone

from typing import Callable

from fastapi import WebSocket, WebSocketDisconnect

from app.clients.ai_service import AsyncAiServiceClient
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.realtime import upload_registry
from app.realtime.answer_timer import DISCONNECTED, SPEECH, AnswerTimer
from app.realtime.deepgram_relay import DeepgramRelay, OnResult
from app.realtime.ws_auth import authenticate_handshake
from app.services.interview_service import InterviewService

log = logging.getLogger(__name__)

# 브라우저가 질문 음성 재생 종료를 알려 주지 않을 때 기다리는 최대 시간 (제안)
AUDIO_END_MAX_SEC = 60.0
POLICY_VIOLATION = 1008  # 인증 실패·남의 응시
INTERNAL_ERROR = 1011  # 서버 오류


def _iso(at: datetime) -> str:
    return at.astimezone(timezone.utc).isoformat()


class InterviewSocketHandler:
    def __init__(
        self, ws: WebSocket, session_id: int, ai: AsyncAiServiceClient,
        relay_factory: Callable[[OnResult], DeepgramRelay] = DeepgramRelay,
    ):
        self.ws, self.session_id, self.ai = ws, session_id, ai
        self.relay_factory = relay_factory
        self.relay: DeepgramRelay | None = None  # 답변 시간에만 열려 있다
        self.events: asyncio.Queue = asyncio.Queue()
        self.order: dict[str, int] = {}  # qkey → 순번 (질문 진행 목록 표시용)
        self.settings: dict = {}

    async def run(self) -> None:
        async with AsyncSessionLocal() as db:
            member = await authenticate_handshake(self.ws, db)
            session = await InterviewService(db).get_own_session(member, self.session_id) if member else None
            if session is None:
                # 연결을 수락하기 전에 닫는다 (본문 5.5)
                await self.ws.close(code=POLICY_VIOLATION)
                return
            try:
                payload = await InterviewService(db).build_start_payload(session)
            except Exception:
                log.exception("면접 %s 시작 본문을 만들지 못했다", self.session_id)
                await self.ws.close(code=INTERNAL_ERROR)
                return
        await self.ws.accept()
        self.settings = payload["settings"]
        self.order = {q["qkey"]: i for i, q in enumerate(payload["questions"], start=1)}
        await self.ws.send_json({"type": "connected", "session_id": self.session_id})
        reader = asyncio.create_task(self._read())
        try:
            actions = (await self.ai.start_interview(self.session_id, payload))["actions"]
            while actions:
                actions = await self.handle_actions(actions)
        except WebSocketDisconnect:
            pass
        except Exception:
            log.exception("면접 %s 처리 중 오류", self.session_id)
            await self._send_error("INTERVIEW_ERROR", "면접 진행 중 오류가 났습니다. 다시 접속해 주세요.")
        finally:
            reader.cancel()

    async def _read(self) -> None:
        """브라우저 메시지를 events 큐에 넣는다. 바이너리(음성 조각)는 답변 시간에만 Deepgram으로 보낸다."""
        try:
            while True:
                msg = await self.ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                if msg.get("bytes"):
                    if self.relay is not None:
                        try:
                            await self.relay.send_audio(msg["bytes"])
                        except Exception as e:
                            log.warning("면접 %s 음성 중계 실패: %s", self.session_id, e)
                elif msg.get("text"):
                    try:
                        await self.events.put(json.loads(msg["text"]))
                    except json.JSONDecodeError:
                        pass
        finally:
            await self.events.put(DISCONNECTED)

    async def _send_error(self, code: str, message: str) -> None:
        try:
            await self.ws.send_json({"type": "error", "code": code, "message": message})
        except Exception:
            pass

    async def handle_actions(self, actions: list[dict]) -> list[dict]:
        """ai-service가 준 행동을 반영한다. 다음에 처리할 행동을 돌려준다. 끝났으면 빈 목록.
        1단계 행동은 present(질문 제시)와 end(종료)다. remove·invalidate·suspend·await_expression은 뒤 단계에서."""
        next_actions: list[dict] = []
        for action in actions:
            if action["type"] == "present":
                next_actions = await self.present(action)
                if next_actions is None:  # 연결이 끊겼다
                    return []
            elif action["type"] == "end":
                await self.end()
                return []
        return next_actions

    async def present(self, action: dict) -> list[dict] | None:
        """질문을 보내고, 생각·답변 시간을 거쳐 답변을 ai-service에 보낸다. 연결이 끊기면 None."""
        question = action["question"]
        qid = question["question_id"]
        await self.send_question(question, action.get("audio_b64"))
        timer = AnswerTimer(self.events, qid)
        if not await timer.wait_audio_end(AUDIO_END_MAX_SEC):
            return None
        think_ends = datetime.now(timezone.utc) + timedelta(seconds=self.settings["think_time_sec"])
        await self.ws.send_json({"type": "phase", "phase": "think", "ends_at": _iso(think_ends)})
        if not await timer.start_think(self.settings["think_time_sec"]):
            return None
        answer_ends = datetime.now(timezone.utc) + timedelta(seconds=self.settings["answer_time_sec"])
        upload_registry.forget(self.session_id, qid)
        await self.open_relay()
        await self.ws.send_json({"type": "phase", "phase": "answer", "ends_at": _iso(answer_ends)})
        reason = await timer.start_answer(self.settings["answer_time_sec"], get_settings().SILENCE_END_SEC)
        raw_text, words = await self.close_relay()
        if reason == "disconnect":
            return None
        await self.ws.send_json({"type": "answer_end", "question_id": qid, "reason": reason})
        await self.ws.send_json({"type": "evaluating", "question_id": qid})
        # 답변이 끝나면 브라우저가 영상을 올린다. 오지 않으면 영상 없이 진행한다
        video_path = await upload_registry.wait(self.session_id, qid, get_settings().VIDEO_UPLOAD_WAIT_SEC)
        if video_path is None:
            log.warning("면접 %s 질문 %s 영상이 오지 않았다", self.session_id, qid)
        resp = await self.ai.submit_answer(self.session_id, {
            "qkey": question["qkey"], "question_id": qid, "bindings": [], "end_reason": reason,
            # Deepgram 단어 시각은 스트림 시작(=답변 시간 시작) 기준이다
            "raw_text": raw_text, "words": words, "answer_start_sec": 0.0, "video_path": video_path,
        })
        async with AsyncSessionLocal() as db:
            await InterviewService(db).persist_answer(self.session_id, qid, video_path, resp["evaluation"])
        return resp["actions"]

    async def open_relay(self) -> None:
        """답변 시간 동안 Deepgram을 연다. 열지 못해도 면접은 이어간다(원문 없이 평가)."""
        async def on_result(text: str, is_final: bool) -> None:
            await self.events.put(SPEECH)
            await self.ws.send_json({"type": "transcript", "text": text, "is_final": is_final})

        relay = self.relay_factory(on_result)
        try:
            await relay.connect()
            self.relay = relay
        except Exception as e:
            log.warning("면접 %s Deepgram 연결 실패: %s", self.session_id, e)

    async def close_relay(self) -> tuple[str, list[dict]]:
        """음성 전달을 멈추고 남은 인식 결과를 받는다."""
        relay, self.relay = self.relay, None
        if relay is None:
            return "", []
        return await relay.close()

    async def send_question(self, question: dict, audio_b64: str | None) -> None:
        """질문 JSON 다음에 음성(wav)을 바이너리로 보낸다 (규약 1.2). is_revealed를 저장한다."""
        async with AsyncSessionLocal() as db:
            await InterviewService(db).mark_presented(question["question_id"])
        await self.ws.send_json({
            "type": "question",
            "question_id": question["question_id"],
            "seq": self.order.get(question["qkey"]),
            "total": len(self.order),
            "text": question["text"],
            "think_sec": self.settings["think_time_sec"],
            "answer_sec": self.settings["answer_time_sec"],
        })
        if audio_b64:
            await self.ws.send_bytes(base64.b64decode(audio_b64))

    async def end(self) -> None:
        """응시 '완료'로 바꾸고 종료를 알린다 (화면 25로 이동)."""
        ended_at = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            await InterviewService(db).finish_session(self.session_id, ended_at)
        await self.ws.send_json({"type": "interview_end", "answered_count": len(self.order), "ended_at": _iso(ended_at)})
        await self.ws.close()
