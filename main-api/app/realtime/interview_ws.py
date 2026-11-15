"""면접 WebSocket 처리 (코드베이스 1. main-api 8장 InterviewSocketHandler, 내부 API 규약 1장).

실시간 면접 1단계 흐름:
  인증 → 응시 확인 → ai-service /start → [질문 + 음성 전송 → 음성 종료 → 생각 시간 → 답변 시간
  → '답변 완료' 또는 시간 종료 → ai-service /answer] 반복 → 종료(응시 '완료')
음성 중계(Deepgram)·영상 업로드 대기는 2단계, 표정 재처리는 3단계, 문의는 5단계에서 넣는다.
연결이 끊기면 응시는 '진행 중'으로 둔다. 다시 연결하면 같은 체크포인트로 이어간다 (아키텍처 9.3).
"""

import asyncio
import base64
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import WebSocket, WebSocketDisconnect

from app.clients.ai_service import AsyncAiServiceClient
from app.db.session import AsyncSessionLocal
from app.realtime.answer_timer import DISCONNECTED, AnswerTimer
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
    def __init__(self, ws: WebSocket, session_id: int, ai: AsyncAiServiceClient):
        self.ws, self.session_id, self.ai = ws, session_id, ai
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
        """브라우저 메시지를 events 큐에 넣는다. 바이너리(음성)는 2단계(Deepgram 중계)에서 쓴다."""
        try:
            while True:
                msg = await self.ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                if msg.get("text"):
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
        await self.ws.send_json({"type": "phase", "phase": "answer", "ends_at": _iso(answer_ends)})
        reason = await timer.start_answer(self.settings["answer_time_sec"])
        if reason == "disconnect":
            return None
        await self.ws.send_json({"type": "answer_end", "question_id": qid, "reason": reason})
        await self.ws.send_json({"type": "evaluating", "question_id": qid})
        # 1단계: STT·영상 없이 보낸다 (2단계에서 원문·단어 시각·영상 경로를 채운다)
        resp = await self.ai.submit_answer(
            self.session_id, {"qkey": question["qkey"], "question_id": qid, "bindings": [], "end_reason": reason}
        )
        return resp["actions"]

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
