"""면접 WebSocket 처리 (코드베이스 1. main-api 8장 InterviewSocketHandler, 내부 API 규약 1장).

흐름:
  인증 → 응시 확인 → ai-service /start → [질문 + 음성 전송 → 음성 종료 → 생각 시간 → 답변 시간
  (브라우저 음성 → Deepgram → 자막) → '답변 완료'·무발화·시간 종료 → 영상 업로드 대기
  → ai-service /answer → 답변·STT·점수 저장 → (표정 실패면) 표정 재분석 대기 → ai-service /expression] 반복
  → 종료(응시 '완료')
문의(5단계): 질문을 받고 답변이 끝나기 전까지 연다. 문의 메시지는 별도 작업(inquiry_loop)이 처리해 질문의 시간은
그대로 흐른다(추가 시간 없음). 판단이 '질문 다시 제시'나 '중단'이면 진행 중인 타이머에 끼어든다.
답변 평가 중에 연 문의는 받아 뒀다가 다음 질문을 낸 뒤 이전 질문부터의 로그로 연다 (AI Agent 설계서 4.5).
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
from app.domain.enums import HandlingStatus, Speaker
from app.realtime import session_events, upload_registry
from app.realtime.answer_timer import DISCONNECTED, INTERRUPT, SPEECH, AnswerTimer, Interrupted
from app.realtime.deepgram_relay import DeepgramRelay, OnResult
from app.realtime.ws_auth import authenticate_handshake
from app.services.inquiry_service import InquiryService
from app.services.interview_service import InterviewService

log = logging.getLogger(__name__)

# 브라우저가 질문 음성 재생 종료를 알려 주지 않을 때 기다리는 최대 시간 (제안)
AUDIO_END_MAX_SEC = 60.0
POLICY_VIOLATION = 1008  # 인증 실패·남의 응시
INTERNAL_ERROR = 1011  # 서버 오류
INQUIRY_TYPES = {"inquiry_open", "inquiry_message", "inquiry_check"}
# 답변 평가 중 문의를 받아 둘 때의 안내 (AI Agent 설계서 4.5 '나중에 정한다', 5단계에서 정함)
INQUIRY_QUEUED = "답변을 처리하고 있습니다. 다음 질문이 나오면 바로 이어서 도와드리겠습니다."
INQUIRY_AFTER_END = "면접 전형이 끝났습니다. 회사에 문의하세요."  # AI Agent 설계서 4.5
CONNECTED_ELSEWHERE = "다른 창에서 면접에 접속해 이 창의 연결을 끊었습니다. 접속한 창에서 이어서 진행해 주세요."
SUSPENDED = {
    False: "문제가 해결되지 않아 면접을 중단했습니다. 다시 접속하면 재시험을 볼 수 있습니다. 면접 마감 전에 응시해 주세요.",
    True: "문제가 해결되지 않아 면접을 중단했습니다. 담당자가 확인한 뒤 내 지원 현황에서 다시 응시할 수 있습니다.",
}


def _iso(at: datetime) -> str:
    return at.astimezone(timezone.utc).isoformat()


# 응시마다 지금 면접을 진행하는 연결. 두 창이 같은 응시를 진행하면 ai-service 그래프 상태가 엇갈렸다
# (통합테스트 IT-INQ-001 세션 627: 재시험이 새 질문을 낸 뒤 바로 '완료'로 끝남). 새 연결이 오면 이전 연결을 끊는다
_connected: dict[int, "InterviewSocketHandler"] = {}


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
        self.seq: dict[str, int | None] = {}  # qkey → interview_question.seq (새 질문이 대신하는 질문의 순번을 이어받는다)
        self.removed: dict | None = None  # 방금 remove·invalidate로 빠진 질문 (다음 present가 그 자리를 이어받는다)
        self.bindings: list[dict] = []  # 새로 저장한 질문의 qkey·question_id 짝. 다음 요청에 실어 보낸다 (규약 2.1)
        self.settings: dict = {}
        # ---------- 문의 (5단계) ----------
        self.inquiry_msgs: asyncio.Queue = asyncio.Queue()
        self.current_qid: int | None = None  # 문의를 열 수 있는 질문 (질문을 낸 뒤 답변이 끝나기 전까지)
        self.inquiry_id: int | None = None  # 진행 중인 문의
        self.pending_open = False  # 답변 평가 중에 받아 둔 문의
        self.inquiry_idle = asyncio.Event()
        self.inquiry_idle.set()
        self.interrupt_actions: list[dict] | None = None  # 문의 판단이 끼어들 때의 다음 행동
        self.handling_status: str | None = None  # 마지막 문의의 처리 상태 (중단 안내)
        self.replaced = False  # 다른 창의 새 연결에 자리를 넘겼다. 이후 행동은 하지 않는다

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
            if payload["resume"]:
                await InquiryService(db).end_abandoned(self.session_id)
        await self.ws.accept()
        previous, _connected[self.session_id] = _connected.get(self.session_id), self
        if previous is not None:
            await previous.close_as_replaced()
        session_events.record(self.session_id, "재연결" if payload["resume"] else "면접 연결")
        self.settings = payload["settings"]
        self.order = {q["qkey"]: i for i, q in enumerate(payload["questions"], start=1)}
        self.seq = {q["qkey"]: q.get("seq") for q in payload["questions"]}
        await self.ws.send_json({"type": "connected", "session_id": self.session_id})
        reader = asyncio.create_task(self._read())
        inquiries = asyncio.create_task(self.inquiry_loop())
        try:
            actions = (await self.ai.start_interview(self.session_id, payload))["actions"]
            while actions:
                actions = await self.handle_actions(actions)
        except WebSocketDisconnect:
            pass
        except Exception as e:
            log.exception("면접 %s 처리 중 오류", self.session_id)
            session_events.record(self.session_id, f"서버 오류: {type(e).__name__}")
            await self._send_error("INTERVIEW_ERROR", "면접 진행 중 오류가 났습니다. 다시 접속해 주세요.")
        finally:
            reader.cancel()
            inquiries.cancel()
            if _connected.get(self.session_id) is self:
                del _connected[self.session_id]

    async def close_as_replaced(self) -> None:
        """다른 창이 같은 응시에 접속했다. 안내하고 이 연결을 닫는다. 진행 중이던 ai-service 요청의 결과는 버린다."""
        self.replaced = True
        session_events.record(self.session_id, "다른 창에서 접속해 이전 연결을 끊음")
        await self._send_error("CONNECTED_ELSEWHERE", CONNECTED_ELSEWHERE)
        try:
            await self.ws.close()
        except Exception:
            pass

    async def _read(self) -> None:
        """브라우저 메시지를 나눈다. 문의는 inquiry_msgs로, 나머지는 타이머가 보는 events로.
        바이너리(음성 조각)는 답변 시간에만 Deepgram으로 보낸다."""
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
                        data = json.loads(msg["text"])
                    except json.JSONDecodeError:
                        continue
                    await (self.inquiry_msgs if data.get("type") in INQUIRY_TYPES else self.events).put(data)
        finally:
            session_events.record(self.session_id, "연결 끊김")
            await self.events.put(DISCONNECTED)

    async def _send_error(self, code: str, message: str) -> None:
        try:
            await self.ws.send_json({"type": "error", "code": code, "message": message})
        except Exception:
            pass

    async def handle_actions(self, actions: list[dict]) -> list[dict]:
        """ai-service가 준 행동을 반영한다. 다음에 처리할 행동을 돌려준다. 끝났으면 빈 목록.
        행동: present(질문 제시), remove(꼬리질문 때문에 빠지는 직무 질문), invalidate(문의 처리로 진행 중이던 질문 무효),
        await_expression(표정 재분석), suspend(응시 중단), end(종료)."""
        next_actions: list[dict] = []
        for action in actions:
            if self.replaced:  # 새 연결이 진행한다
                return []
            if action["type"] == "remove":
                await self.remove(action["question"])
            elif action["type"] == "invalidate":
                await self.invalidate(action["question"], action.get("keep_question", False))
            elif action["type"] == "present":
                next_actions = await self.present(action)
                if next_actions is None:  # 연결이 끊겼다
                    return []
            elif action["type"] == "await_expression":
                next_actions = await self.rescore_with_expression(action["question"])
            elif action["type"] == "suspend":
                await self.suspend()
                return []
            elif action["type"] == "end":
                await self.end()
                return []
        return next_actions

    async def remove(self, question: dict) -> None:
        """빠진 질문을 '무효'로 바꾼다. 질문 진행 목록의 그 순번은 다음에 제시할 꼬리질문이 이어받는다."""
        async with AsyncSessionLocal() as db:
            await InterviewService(db).invalidate_question(question["question_id"])
        self.removed = question

    async def invalidate(self, question: dict, keep_question: bool) -> None:
        """문의 처리로 진행 중이던 질문과 답변을 무효로 한다. 기업 질문은 질문을 두고 답변만 (규약 2.1)."""
        if question.get("question_id") is None:
            return
        async with AsyncSessionLocal() as db:
            await InterviewService(db).invalidate_presented(self.session_id, question["question_id"], keep_question)
        if not keep_question:
            self.removed = question

    async def bind_new_question(self, question: dict) -> dict:
        """question_id가 없는 새 질문(꼬리질문, 대체 질문)을 저장하고 짝을 남긴다. 순번은 빠진 질문의 것을 이어받는다."""
        replaced = self.removed or {}
        self.removed = None
        # 대체되는 질문도 새로 만든 질문이었다면 ai-service는 그 키(r…·꼬리질문 키)로, 재접속한 main-api는 q{id}로 안다
        key = replaced.get("qkey")
        if key not in self.seq and replaced.get("question_id") is not None:
            key = f"q{replaced['question_id']}"
        async with AsyncSessionLocal() as db:
            qid = await InterviewService(db).save_new_question(self.session_id, question, self.seq.get(key))
        self.bindings.append({"qkey": question["qkey"], "question_id": qid})
        self.seq[question["qkey"]] = self.seq.get(key)
        if key in self.order:
            self.order[question["qkey"]] = self.order.pop(key)
        else:  # 재접속으로 다시 온 새 질문: 진행 목록 끝에 둔다
            self.order.setdefault(question["qkey"], len(self.order) + 1)
        return question | {"question_id": qid}

    def take_bindings(self) -> list[dict]:
        bindings, self.bindings = self.bindings, []
        return bindings

    def take_interrupt(self) -> list[dict] | None:
        actions, self.interrupt_actions = self.interrupt_actions, None
        return actions

    async def present(self, action: dict) -> list[dict] | None:
        """질문을 보내고, 생각·답변 시간을 거쳐 답변을 ai-service에 보낸다. 연결이 끊기면 None.
        문의 판단이 끼어들면 답변을 보내지 않고 그 행동을 돌려준다."""
        question = action["question"]
        if question.get("question_id") is None:
            question = await self.bind_new_question(question)
        qid = question["question_id"]
        await self.send_question(question, action.get("audio_b64"))
        timer = AnswerTimer(self.events, qid, self.take_interrupt)
        try:
            if not await timer.wait_audio_end(AUDIO_END_MAX_SEC):
                return None
            think_ends = datetime.now(timezone.utc) + timedelta(seconds=self.settings["think_time_sec"])
            await self.ws.send_json({"type": "phase", "phase": "think", "ends_at": _iso(think_ends)})
            session_events.record(self.session_id, "생각 시간 시작")
            if not await timer.start_think(self.settings["think_time_sec"]):
                return None
            answer_ends = datetime.now(timezone.utc) + timedelta(seconds=self.settings["answer_time_sec"])
            upload_registry.forget(self.session_id, qid)
            await self.open_relay()
            await self.ws.send_json({"type": "phase", "phase": "answer", "ends_at": _iso(answer_ends)})
            session_events.record(self.session_id, "답변 시간 시작")
            reason = await timer.start_answer(self.settings["answer_time_sec"], get_settings().SILENCE_END_SEC)
        except Interrupted as e:
            await self.close_relay()
            self.current_qid = None
            return e.actions
        raw_text, words = await self.close_relay()
        if reason == "disconnect":
            return None
        self.current_qid = None
        await self.ws.send_json({"type": "answer_end", "question_id": qid, "reason": reason})
        await self.ws.send_json({"type": "evaluating", "question_id": qid})
        session_events.record(self.session_id, f"답변 종료 ({reason})")
        # 문의 중이면 끝나기를 기다린다. ai-service는 문의 중에는 답변을 받지 않는다
        await self.inquiry_idle.wait()
        if (actions := self.take_interrupt()) is not None:
            return actions  # 문의 판단으로 이 질문을 다시 제시하거나 중단한다. 이 답변은 보내지 않는다
        # 답변이 끝나면 브라우저가 영상을 올린다. 오지 않으면 영상 없이 진행한다
        video_path = await upload_registry.wait(self.session_id, qid, get_settings().VIDEO_UPLOAD_WAIT_SEC)
        if video_path is None:
            log.warning("면접 %s 질문 %s 영상이 오지 않았다", self.session_id, qid)
            session_events.record(self.session_id, "답변 영상이 올라오지 않음")
        resp = await self.ai.submit_answer(self.session_id, {
            "qkey": question["qkey"], "question_id": qid, "bindings": self.take_bindings(), "end_reason": reason,
            # Deepgram 단어 시각은 스트림 시작(=답변 시간 시작) 기준이다
            "raw_text": raw_text, "words": words, "answer_start_sec": 0.0, "video_path": video_path,
        })
        async with AsyncSessionLocal() as db:
            await InterviewService(db).persist_answer(self.session_id, qid, video_path, resp["evaluation"])
        return resp["actions"]

    async def rescore_with_expression(self, question: dict) -> list[dict]:
        """표정 분석이 실패한 답변을 worker가 다시 분석하게 하고, 끝나면 그 표정으로 답변 점수를 받는다 (아키텍처 8).
        재분석도 실패하거나 EXPRESSION_WAIT_SEC를 넘기면 표정 없이 보낸다. 지원자는 이 동안 다음 질문을 기다린다."""
        async with AsyncSessionLocal() as db:
            service = InterviewService(db)
            requested = await service.request_expression_reprocess(self.session_id, question["question_id"])
            if requested is None:
                raise RuntimeError(f"질문 {question['question_id']}의 저장된 답변이 없습니다")
            job_id, answer_id = requested
            answer = await service.wait_expression(job_id, answer_id, get_settings().EXPRESSION_WAIT_SEC)
            resp = await self.ai.submit_expression(self.session_id, {
                "qkey": question["qkey"], "answer_id": answer_id, "bindings": self.take_bindings(),
                "main_expression": answer.main_expression, "expression_ratio": answer.expression_ratio,
            })
            await service.save_expression_result(answer_id, resp["expression_score"], resp["answer_score"])
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
            session_events.record(self.session_id, f"음성 인식 연결 실패: {type(e).__name__}")

    async def close_relay(self) -> tuple[str, list[dict]]:
        """음성 전달을 멈추고 남은 인식 결과를 받는다."""
        relay, self.relay = self.relay, None
        if relay is None:
            return "", []
        return await relay.close()

    async def send_question(self, question: dict, audio_b64: str | None) -> None:
        """질문 JSON 다음에 음성(wav)을 바이너리로 보낸다 (규약 1.2). is_revealed를 저장한다.
        답변 평가 중에 받아 둔 문의가 있으면 이어서 연다."""
        async with AsyncSessionLocal() as db:
            await InterviewService(db).mark_presented(question["question_id"])
        session_events.question_started(self.session_id, f"질문 제시 (question_id {question['question_id']})")
        await self.ws.send_json({
            "type": "question",
            "question_id": question["question_id"],
            # 재접속해 다시 낸 새 질문(꼬리질문·대체 질문)은 ai-service가 f…·r…로, 재접속한 main-api는 q{id}로 안다
            "seq": self.order.get(question["qkey"]) or self.order.get(f"q{question['question_id']}"),
            "total": len(self.order),
            "text": question["text"],
            "think_sec": self.settings["think_time_sec"],
            "answer_sec": self.settings["answer_time_sec"],
        })
        if audio_b64:
            await self.ws.send_bytes(base64.b64decode(audio_b64))
        self.current_qid = question["question_id"]
        if self.pending_open:
            self.pending_open = False
            await self.inquiry_msgs.put({"type": "inquiry_open", "deferred": True})

    async def suspend(self) -> None:
        """응시 '중단'. 관리자 처리가 필요한지 알리고 연결을 닫는다 (규약 1.2 suspended, APP-013·014)."""
        async with AsyncSessionLocal() as db:
            await InterviewService(db).suspend_session(self.session_id)
        needs_admin = self.handling_status == HandlingStatus.ADMIN_WAITING.value
        session_events.record(self.session_id, "면접 중단")
        await self.ws.send_json({"type": "suspended", "message": SUSPENDED[needs_admin], "needs_admin": needs_admin})
        await self.ws.close()

    async def end(self) -> None:
        """응시 '완료'로 바꾸고 종료를 알린다 (화면 25로 이동)."""
        ended_at = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            await InterviewService(db).finish_session(self.session_id, ended_at)
        if self.pending_open:  # 마지막 답변 뒤에 연 문의는 처리하지 않는다 (AI Agent 설계서 4.5)
            await self.ws.send_json({"type": "inquiry_reply", "inquiry_id": None, "text": INQUIRY_AFTER_END, "check": None})
        await self.ws.send_json({"type": "interview_end", "answered_count": len(self.order), "ended_at": _iso(ended_at)})
        await self.ws.close()

    # ---------- 문의 (5단계, 규약 1.1·1.2·2.4) ----------
    async def inquiry_loop(self) -> None:
        """문의 메시지를 하나씩 처리한다. 질문의 시간은 그대로 흐른다."""
        while True:
            msg = await self.inquiry_msgs.get()
            try:
                if msg["type"] == "inquiry_open":
                    await self.open_inquiry(previous=msg.get("deferred", False))
                elif msg.get("inquiry_id") == self.inquiry_id and self.inquiry_id is not None:
                    if msg["type"] == "inquiry_message":
                        await self.inquiry_message(str(msg.get("text") or ""))
                    else:
                        await self.inquiry_check(bool(msg.get("resolved")))
            except Exception:
                log.exception("면접 %s 문의 처리 중 오류", self.session_id)
                session_events.record(self.session_id, "문의 처리 오류")
                await self._send_error("INQUIRY_ERROR", "문의를 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.")

    async def open_inquiry(self, previous: bool) -> None:
        """질문을 받고 답변이 끝나기 전이면 연다. 답변 평가 중이면 받아 두고 다음 질문을 낸 뒤 연다.
        로그는 진행 중인 질문이 시작된 때부터, 받아 둔 문의는 이전 질문이 시작된 때부터 (AI Agent 설계서 4.5)."""
        if self.inquiry_id is not None:
            return
        if self.current_qid is None:
            if not self.pending_open:
                self.pending_open = True
                await self.ws.send_json({"type": "inquiry_reply", "inquiry_id": None, "text": INQUIRY_QUEUED, "check": None})
            return
        self.inquiry_idle.clear()
        logs = session_events.since_question(self.session_id, previous=previous)
        async with AsyncSessionLocal() as db:
            inquiry_id = await InquiryService(db).open(self.session_id, self.current_qid, logs)
        self.inquiry_id = inquiry_id
        session_events.record(self.session_id, "기술 문의 시작")
        resp = await self.ai.send_inquiry(self.session_id, {
            "inquiry_id": inquiry_id, "event": "open", "system_logs": logs, "bindings": self.take_bindings(),
        })
        await self.ws.send_json({"type": "inquiry_opened", "inquiry_id": inquiry_id})
        await self._reply(resp)

    async def inquiry_message(self, text: str) -> None:
        async with AsyncSessionLocal() as db:
            await InquiryService(db).add_message(self.inquiry_id, Speaker.APPLICANT.value, text)
        resp = await self.ai.send_inquiry(self.session_id, {"inquiry_id": self.inquiry_id, "event": "message", "text": text})
        await self._reply(resp)

    async def inquiry_check(self, resolved: bool) -> None:
        """해결 확인 결과. 시스템 재검사(브라우저가 마이크·카메라를 다시 검사) 또는 지원자 확인으로 온다."""
        session_events.record(self.session_id, f"해결 확인: {'해결' if resolved else '미해결'}")
        resp = await self.ai.send_inquiry(self.session_id, {"inquiry_id": self.inquiry_id, "event": "check", "resolved": resolved})
        await self._reply(resp)
        if (j := resp.get("judgment")) is not None:
            await self.close_inquiry(j, resp.get("actions", []))

    async def _reply(self, resp: dict) -> None:
        if resp.get("reply"):
            async with AsyncSessionLocal() as db:
                await InquiryService(db).add_message(self.inquiry_id, Speaker.CHATBOT.value, resp["reply"])
            await self.ws.send_json({"type": "inquiry_reply", "inquiry_id": self.inquiry_id, "text": resp["reply"],
                                     "check": resp.get("check")})

    async def close_inquiry(self, judgment: dict, actions: list[dict]) -> None:
        """판단을 저장하고 결과를 알린다 (규약 1.2 inquiry_result). 질문 다시 제시·중단이면 진행 중인 질문에 끼어든다."""
        inquiry_id, self.inquiry_id = self.inquiry_id, None
        async with AsyncSessionLocal() as db:
            self.handling_status, follow_up = await InquiryService(db).close(inquiry_id, judgment)
        session_events.record(self.session_id, f"기술 문의 종료: {self.handling_status}")
        await self.ws.send_json({"type": "inquiry_result", "inquiry_id": inquiry_id, "resolved": judgment["resolved"],
                                 "cause": judgment["cause"], "follow_up": follow_up})
        if actions:
            self.interrupt_actions = actions
            await self.events.put(INTERRUPT)
        self.inquiry_idle.set()
