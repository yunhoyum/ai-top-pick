"""면접 그래프 빌더 (ai-service 3.5, AI Agent 설계서 4.1·4.4).

흐름:
  START → load_question → (queue 비었음) end_interview → END
                        → present_question → wait_answer(interrupt) → evaluate_answer
                          → (표정 실패) wait_expression(interrupt) → score_answer
                          → score_answer → (꼬리질문 조건) follow_up → (만듦) present_question / (못 만듦) load_question
                                         → load_question
                        wait_answer → (문의) inquiry_wait(interrupt) → inquiry_analyze → check_resolved(interrupt)
                          → wait_answer / invalidate_and_represent → present_question / inquiry_analyze
                          / suspend(interrupt) → (재접속) invalidate_and_represent
thread_id는 session-{session_id}다. 재접속·재시험은 같은 체크포인트로 이어간다.
"""

import base64
import time

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from app.graphs.interview.inquiry_nodes import route_after_inquiry_wait, route_after_judgment
from app.graphs.interview.nodes import Deps, Tts, make_nodes
from app.graphs.interview.routes import (
    route_after_eval,
    route_after_follow_up,
    route_after_load,
    route_after_score,
    route_after_wait,
)
from app.graphs.interview.state import InterviewState
from app.schemas.internal import AnswerRequest, ExpressionRequest, InquiryRequest, StartInterviewRequest


class NoCheckpointError(Exception):
    """재접속(resume=참)인데 체크포인트가 없다. 처음부터 시작하지 않는다. 답변 중복 저장을 막기 위해서다."""


class GraphBusyError(Exception):
    """재접속했는데 이전 연결의 요청(답변 채점 등)이 기다리는 시간 안에 끝나지 않았다."""


# 재접속 때 이전 연결의 요청이 끝나기를 기다리는 시간. 답변 채점은 LLM을 여러 번 불러 수십 초 걸린다 (제안)
RESUME_WAIT_SEC = 300.0
RESUME_POLL_SEC = 0.5


class NotWaitingError(Exception):
    """답변을 받을 상태가 아니거나, 답변한 질문이 지금 질문이 아니다."""


def build_interview_graph(checkpointer: BaseCheckpointSaver, deps: Deps):
    nodes = make_nodes(deps)
    g = StateGraph(InterviewState)
    for name, fn in nodes.items():
        g.add_node(name, fn)
    g.add_edge(START, "load_question")
    g.add_conditional_edges("load_question", route_after_load, ["present_question", "end_interview"])
    g.add_edge("present_question", "wait_answer")
    g.add_conditional_edges("wait_answer", route_after_wait, ["evaluate_answer", "inquiry_wait"])
    g.add_conditional_edges("inquiry_wait", route_after_inquiry_wait, ["wait_answer", "inquiry_analyze"])
    g.add_edge("inquiry_analyze", "check_resolved")
    g.add_conditional_edges("check_resolved", route_after_judgment,
                            ["wait_answer", "invalidate_and_represent", "inquiry_analyze", "suspend"])
    g.add_edge("suspend", "invalidate_and_represent")
    g.add_edge("invalidate_and_represent", "present_question")
    g.add_conditional_edges("evaluate_answer", route_after_eval, ["wait_expression", "score_answer"])
    g.add_edge("wait_expression", "score_answer")
    g.add_conditional_edges("score_answer", route_after_score, ["follow_up", "load_question"])
    g.add_conditional_edges("follow_up", route_after_follow_up, ["present_question", "load_question"])
    g.add_edge("end_interview", END)
    return g.compile(checkpointer=checkpointer)


def graph_config(session_id: int) -> dict:
    return {"configurable": {"thread_id": f"session-{session_id}"}}


def _waiting_question(graph, config, node: str = "wait_answer") -> dict | None:
    """node에서 멈춰 있으면 지금 질문, 아니면 None."""
    snapshot = graph.get_state(config)
    return snapshot.values.get("current") if node in snapshot.next else None


def _wait_until_paused(graph, config, wait_sec: float):
    """다른 요청이 그래프를 진행 중이면(다음 노드는 있는데 멈춘 interrupt가 없음) 멈추거나 끝날 때까지 기다린다."""
    deadline = time.monotonic() + wait_sec
    while True:
        snapshot = graph.get_state(config)
        if not snapshot.next or any(task.interrupts for task in snapshot.tasks):
            return snapshot
        if time.monotonic() >= deadline:
            raise GraphBusyError(config["configurable"]["thread_id"])
        time.sleep(RESUME_POLL_SEC)


def start_or_resume(graph, req: StartInterviewRequest, tts: Tts, wait_sec: float = RESUME_WAIT_SEC) -> list[dict]:
    """체크포인트가 없으면 새로 시작한다. 있으면 마지막 상태에서 이어간다 (재접속).
    이전 연결의 요청이 아직 그래프를 진행 중이면 멈출 때까지 기다린다. 통합테스트 재수행 세션 796: 답변 채점 중에
    새로고침하자 멈춘 상태가 아니라서 '이미 끝난 면접'으로 보고 응시를 '완료'로 끝냈다.
    답변을 기다리던 중이면 그 질문을 다시 돌려준다. 음성도 다시 만든다 (SYS-011: 다시 제시한 질문도 다시 읽어준다).
    중단(재접속 대기) 상태면 interrupt를 풀어 진행 중이던 질문을 무효로 하고 다시 제시한다 (재시험, APP-014).
    문의 도중 끊겼으면 문의를 끝내고 진행 중이던 질문을 다시 제시한다 (5단계 결정)."""
    config = graph_config(req.session_id)
    snapshot = graph.get_state(config)
    if snapshot.values:
        snapshot = _wait_until_paused(graph, config, wait_sec)
    if not snapshot.values:
        if req.resume:
            raise NoCheckpointError(req.session_id)
        state = graph.invoke(
            {
                "session_id": req.session_id,
                "posting_id": req.posting_id,
                "settings": req.settings.model_dump(),
                "queue": [q.model_dump() for q in req.questions],
                "current": None,
                "answered": [],
                "follow_up_counts": {},
                "posting": req.posting.model_dump(),
                "documents": req.documents.model_dump(),
                "actions": [],
            },
            config,
        )
        return state["actions"]
    if _waiting_question(graph, config, "suspend"):
        return graph.invoke(Command(resume={"type": "reconnect"}), config)["actions"]
    if _waiting_question(graph, config, "inquiry_wait") or _waiting_question(graph, config, "check_resolved"):
        graph.invoke(Command(resume={"event": "cancel"}), config)
    if current := _waiting_question(graph, config):
        audio = base64.b64encode(tts(current["text"])).decode("ascii")
        if current.get("question_id") is not None:
            return [{"type": "present", "question": current, "audio_b64": audio}]
        return _represent_new_question(graph.get_state(config).values, current, audio, req.questions)
    if current := _waiting_question(graph, config, "wait_expression"):
        # 답변은 이미 받았고 표정 재분석을 기다리던 중에 끊겼다. main-api가 다시 분석해 /expression을 보낸다
        return [{"type": "await_expression", "question": current}]
    return [{"type": "end"}]  # 이미 끝난 면접


def _represent_new_question(state: dict, current: dict, audio: str, questions: list) -> list[dict]:
    """question_id를 아직 모르는 새 질문(꼬리질문·대체 질문)을 재접속에서 다시 낸다.
    main-api가 이미 저장했으면(질문 목록에 같은 글이 있음) 그 question_id로 낸다. 다시 저장하면 중복된다.
    저장하지 않았으면 이전 연결이 마지막 요청의 행동을 반영하지 못한 것이다. 그 행동(질문 제거·무효)을 함께 낸다.
    빠진 질문의 순번을 새 질문이 이어받으려면 main-api가 제거를 먼저 알아야 한다 (통합테스트 재수행 세션 797)."""
    queued = {q["qkey"] for q in state.get("queue", [])}
    saved = next((q for q in questions if q.question_id is not None and q.text == current["text"]
                  and q.qkey not in queued), None)
    if saved is not None:
        return [{"type": "present", "question": current | {"question_id": saved.question_id}, "audio_b64": audio}]
    unapplied = [a for a in state.get("actions", []) if a["type"] in ("remove", "invalidate")]
    return unapplied + [{"type": "present", "question": current, "audio_b64": audio}]


def submit_answer(graph, session_id: int, req: AnswerRequest) -> tuple[dict, list[dict]]:
    """답변으로 interrupt를 풀고 (답변 평가, 다음 행동)을 돌려준다."""
    config = graph_config(session_id)
    current = _waiting_question(graph, config)
    if current is None or current["qkey"] != req.qkey:
        raise NotWaitingError(req.qkey)
    # bindings(새 질문의 question_id 짝)는 wait_answer가 지금 질문에 반영한다
    state = graph.invoke(Command(resume={"type": "answer", **req.model_dump()}), config)
    return state["last_evaluation"], state["actions"]


def submit_expression(graph, session_id: int, req: ExpressionRequest) -> tuple[dict, list[dict]]:
    """다시 분석한 표정으로 interrupt를 풀고 (답변 평가, 다음 행동)을 돌려준다 (규약 2.5)."""
    config = graph_config(session_id)
    current = _waiting_question(graph, config, "wait_expression")
    if current is None or current["qkey"] != req.qkey:
        raise NotWaitingError(req.qkey)
    state = graph.invoke(Command(resume=req.model_dump()), config)
    return state["last_evaluation"], state["actions"]


# 이벤트마다 받을 수 있는 interrupt. 해결 확인을 기다리는 중에도 지원자가 글로 더 알려 줄 수 있다
INQUIRY_NODE = {"open": {"wait_answer"}, "message": {"inquiry_wait", "check_resolved"}, "check": {"check_resolved"}}


def submit_inquiry(graph, session_id: int, req: InquiryRequest) -> dict:
    """문의 요청으로 interrupt를 푼다 (규약 2.4). 문의는 답변을 기다릴 때만 시작할 수 있다 (AI Agent 설계서 4.5).
    {reply, check, judgment, actions}를 돌려준다."""
    config = graph_config(session_id)
    snapshot = graph.get_state(config)
    inquiry = snapshot.values.get("inquiry")
    if not INQUIRY_NODE[req.event] & set(snapshot.next):
        raise NotWaitingError(req.event)
    if req.event != "open" and (inquiry is None or inquiry["inquiry_id"] != req.inquiry_id):
        raise NotWaitingError(req.inquiry_id)
    value = {"type": "inquiry", **req.model_dump()}
    if req.event != "open":  # 문의 서브그래프 안의 interrupt는 문의 이벤트만 받는다
        value = req.model_dump()
    state = graph.invoke(Command(resume=value), config)
    return {"reply": state.get("inquiry_reply"), "check": state.get("inquiry_check"),
            "judgment": state.get("inquiry_judgment"), "actions": state.get("actions", [])}
