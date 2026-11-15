"""면접 그래프 빌더 (ai-service 3.5, AI Agent 설계서 4.1·4.4).

흐름 (꼬리질문·문의는 4·5단계):
  START → load_question → (queue 비었음) end_interview → END
                        → present_question → wait_answer(interrupt) → evaluate_answer
                          → (표정 실패) wait_expression(interrupt) → score_answer → load_question
                          → score_answer → load_question
thread_id는 session-{session_id}다. 재접속·재시험은 같은 체크포인트로 이어간다.
"""

import base64

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from app.graphs.interview.nodes import Deps, Tts, make_nodes
from app.graphs.interview.routes import route_after_eval, route_after_load, route_after_wait
from app.graphs.interview.state import InterviewState
from app.schemas.internal import AnswerRequest, ExpressionRequest, StartInterviewRequest


class NoCheckpointError(Exception):
    """재접속(resume=참)인데 체크포인트가 없다. 처음부터 시작하지 않는다. 답변 중복 저장을 막기 위해서다."""


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
    g.add_conditional_edges("wait_answer", route_after_wait, ["evaluate_answer"])
    g.add_conditional_edges("evaluate_answer", route_after_eval, ["wait_expression", "score_answer"])
    g.add_edge("wait_expression", "score_answer")
    g.add_edge("score_answer", "load_question")
    g.add_edge("end_interview", END)
    return g.compile(checkpointer=checkpointer)


def graph_config(session_id: int) -> dict:
    return {"configurable": {"thread_id": f"session-{session_id}"}}


def _waiting_question(graph, config, node: str = "wait_answer") -> dict | None:
    """node에서 멈춰 있으면 지금 질문, 아니면 None."""
    snapshot = graph.get_state(config)
    return snapshot.values.get("current") if node in snapshot.next else None


def start_or_resume(graph, req: StartInterviewRequest, tts: Tts) -> list[dict]:
    """체크포인트가 없으면 새로 시작한다. 있으면 마지막 상태에서 이어간다 (재접속).
    답변을 기다리던 중이면 그 질문을 다시 돌려준다. 음성도 다시 만든다 (SYS-011: 다시 제시한 질문도 다시 읽어준다).
    중단(재접속 대기) 상태의 재시험은 5단계에서 넣는다."""
    config = graph_config(req.session_id)
    snapshot = graph.get_state(config)
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
    if current := _waiting_question(graph, config):
        audio = base64.b64encode(tts(current["text"])).decode("ascii")
        return [{"type": "present", "question": current, "audio_b64": audio}]
    if current := _waiting_question(graph, config, "wait_expression"):
        # 답변은 이미 받았고 표정 재분석을 기다리던 중에 끊겼다. main-api가 다시 분석해 /expression을 보낸다
        return [{"type": "await_expression", "question": current}]
    return [{"type": "end"}]  # 이미 끝난 면접


def submit_answer(graph, session_id: int, req: AnswerRequest) -> tuple[dict, list[dict]]:
    """답변으로 interrupt를 풀고 (답변 평가, 다음 행동)을 돌려준다."""
    config = graph_config(session_id)
    current = _waiting_question(graph, config)
    if current is None or current["qkey"] != req.qkey:
        raise NotWaitingError(req.qkey)
    # bindings(새 질문의 question_id 짝)는 꼬리질문·대체 질문이 생기는 4·5단계에서 반영한다
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
