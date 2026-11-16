"""문의 서브그래프 노드 (ai-service 3.4, AI Agent 설계서 6장, SYS-003, APP-013·014).

  wait_answer(문의 시작) → inquiry_wait(interrupt: 지원자 메시지) → inquiry_analyze(원인·해결방안·결함 원인, 안내)
  → check_resolved(interrupt: 해결 확인) → route_after_judgment
      해결 + 지원자 측            → wait_answer (진행 중이던 질문 그대로)
      해결 + 시스템 측·판단 불가  → invalidate_and_represent → present_question
      미해결, 시도 3회 미만        → inquiry_analyze (앞에서 안내한 방법을 빼고 다시)
      지원자가 글을 더 보냄        → inquiry_analyze (그 글을 붙여 다시. 실패로 세지 않는다)
      미해결 3회                  → suspend(interrupt: 재접속 대기) → (재접속, /start) invalidate_and_represent
해결 확인은 시스템이 다시 검사할 수 있는 문제(마이크·카메라 입력)면 브라우저 재검사 결과로, 아니면 지원자 확인으로 받는다.
문의 도중 연결이 끊겨 재접속하면 문의를 끝내고 진행 중이던 질문을 다시 제시한다 (cancel, 5단계 결정).
"""

import logging
import uuid
from typing import Callable

from langgraph.types import interrupt

from app.graphs.interview.state import InterviewState
from app.prompts.inquiry import GREETING

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3  # 해결방안대로 시도했지만 실패한 횟수 (SYS-003)
CHATBOT, APPLICANT = "챗봇", "지원자"  # chat_message.speaker

HANDLING = {  # → inquiry.handling_detail. 후속 조치를 코드가 쓴다 (judgment_type.follow_up과 같은 뜻)
    ("resolved", "지원자 측"): "해결되어 진행 중이던 질문을 그대로 이어서 진행했다.",
    ("resolved", "other"): "해결되어 진행 중이던 질문과 답변을 무효로 하고 질문을 다시 제시했다.",
    ("unresolved", "지원자 측"): f"{MAX_ATTEMPTS}회 시도해도 해결되지 않아 면접을 중단했다. 지원자는 바로 재접속해 재시험을 볼 수 있다.",
    ("unresolved", "other"): f"{MAX_ATTEMPTS}회 시도해도 해결되지 않아 면접을 중단했다. 관리자가 처리한 뒤 재시험을 볼 수 있다.",
}

Analyze = Callable[[list[dict], list[dict], list[str]], dict]  # (대화, 로그, 앞에서 안내한 방법) → InquiryAnalysis
Replace = Callable[[dict, dict, str, list[str]], str]  # (공고, 지원자 서류, 질문 유형, 이미 나온 질문) → 대체 AI 질문
FollowUp = Callable[[dict], str | None]


def start_inquiry(value: dict) -> dict:
    """wait_answer가 문의 시작을 받았을 때 State에 넣을 값. interrupt 앞에서 넣어야 남으므로 wait_answer가 부른다."""
    return {
        "inquiry": {"inquiry_id": value["inquiry_id"], "messages": [{"speaker": CHATBOT, "text": GREETING}],
                    "logs": value.get("system_logs", []), "tried": [], "analysis": None, "ai_attempt_count": 0,
                    "cancelled": False, "resolved": None},
        "inquiry_reply": GREETING, "inquiry_check": None, "inquiry_judgment": None,
    }


def _judgment(inquiry: dict, resolved: bool) -> dict:
    a = inquiry["analysis"]
    key = ("resolved" if resolved else "unresolved", "지원자 측" if a["cause"] == "지원자 측" else "other")
    return {"resolved": resolved, "cause": a["cause"], "judgment_basis": a["problem"],
            "ai_action": " / ".join(inquiry["tried"]), "handling_detail": HANDLING[key],
            "ai_attempt_count": inquiry["ai_attempt_count"]}


def make_inquiry_nodes(analyze: Analyze, replace: Replace, follow_up: FollowUp,
                       follow_up_inputs: Callable[[InterviewState, dict], dict]) -> dict[str, Callable]:
    def inquiry_wait(state: InterviewState) -> dict:
        """지원자 메시지를 기다린다 (워크플로우 6-2)."""
        value = interrupt({"waiting": "inquiry_message", "inquiry_id": state["inquiry"]["inquiry_id"]})
        if value.get("event") == "cancel":
            return {"inquiry": state["inquiry"] | {"cancelled": True}, "actions": []}
        messages = state["inquiry"]["messages"] + [{"speaker": APPLICANT, "text": value.get("text") or ""}]
        logs = state["inquiry"]["logs"] + value.get("system_logs", [])
        return {"inquiry": state["inquiry"] | {"messages": messages, "logs": logs}, "actions": [],
                "inquiry_reply": None, "inquiry_check": None, "inquiry_judgment": None}

    def inquiry_analyze(state: InterviewState) -> dict:
        """T-21 결함 분석 + T-22 해결방안 안내. 다시 시도할 때는 앞에서 안내한 방법을 빼고 묻는다."""
        inq = state["inquiry"]
        a = analyze(inq["messages"], inq["logs"], inq["tried"])
        inq = inq | {"analysis": a, "tried": inq["tried"] + [a["solution"]],
                     "messages": inq["messages"] + [{"speaker": CHATBOT, "text": a["reply"]}]}
        return {"inquiry": inq, "inquiry_reply": a["reply"], "inquiry_check": "system" if a["system_checkable"] else "applicant"}

    def check_resolved(state: InterviewState) -> dict:
        """T-23 해결 확인. 실패하면 ai_attempt_count +1. 판단이 끝나면(해결 또는 3회 실패) 판단 결과를 남긴다.
        3회 실패면 '중단'을 넣는다. 다음 suspend 노드는 interrupt만 하므로 여기서 넣어야 남는다."""
        value = interrupt({"waiting": "inquiry_check", "inquiry_id": state["inquiry"]["inquiry_id"]})
        inq = state["inquiry"]
        if value.get("event") == "cancel":
            return {"inquiry": inq | {"cancelled": True}, "actions": []}
        base = {"actions": [], "inquiry_reply": None, "inquiry_check": None}
        if value.get("event") == "message":
            # 해결 확인 대신 지원자가 글로 더 알려 줬다(챗봇이 자세히 물은 경우 등). 그 글로 다시 분석한다
            messages = inq["messages"] + [{"speaker": APPLICANT, "text": value.get("text") or ""}]
            logs = inq["logs"] + value.get("system_logs", [])
            return base | {"inquiry": inq | {"messages": messages, "logs": logs, "resolved": None}, "inquiry_judgment": None}
        if value.get("resolved"):
            inq = inq | {"resolved": True}
            return base | {"inquiry": inq, "inquiry_judgment": _judgment(inq, True)}
        inq = inq | {"resolved": False, "ai_attempt_count": inq["ai_attempt_count"] + 1}
        if inq["ai_attempt_count"] < MAX_ATTEMPTS:
            return base | {"inquiry": inq, "inquiry_judgment": None}
        return base | {"inquiry": inq, "inquiry_judgment": _judgment(inq, False), "actions": [{"type": "suspend"}]}

    def suspend(state: InterviewState) -> dict:
        """그래프를 끝내지 않고 재접속을 기다린다 (워크플로우 6-8~11). 재접속하면 /start가 풀고 질문을 다시 제시한다."""
        interrupt({"waiting": "reconnect"})
        return {"actions": [], "inquiry_judgment": None, "inquiry_reply": None}

    def invalidate_and_represent(state: InterviewState) -> dict:
        """진행 중이던 질문을 무효로 하고 다시 제시할 질문을 만든다 (T-24, 워크플로우 6-11, APP-014).
        기업 질문은 같은 질문(답변만 무효), AI 질문은 같은 유형의 새 질문, 꼬리질문은 그 꼬리질문을 만든
        직전 답변으로 새 꼬리질문. 무효 처리한 꼬리질문은 개수에서 빼고 새 꼬리질문을 센다."""
        current = state["current"]
        kind = current.get("kind")
        actions = state.get("actions", []) + [{"type": "invalidate", "question": current, "keep_question": kind == "기업"}]
        if kind == "기업":
            return {"actions": actions, "inquiry": None}
        qkey = f"r{uuid.uuid4().hex}"
        if kind == "꼬리":
            text = follow_up(follow_up_inputs(state, current)) or current["text"]  # 못 만들면 같은 문장을 새로 제시
            new = current | {"qkey": qkey, "question_id": None, "text": text}
        else:
            existing = [h["question"]["text"] for h in state.get("history", [])] + [q["text"] for q in state.get("queue", [])]
            text = replace(state["posting"], state["documents"], current.get("question_type") or "직무",
                           existing + [current["text"]])
            new = current | {"qkey": qkey, "question_id": None, "text": text}
        return {"actions": actions, "current": new, "inquiry": None}

    return {
        "inquiry_wait": inquiry_wait,
        "inquiry_analyze": inquiry_analyze,
        "check_resolved": check_resolved,
        "suspend": suspend,
        "invalidate_and_represent": invalidate_and_represent,
    }


def route_after_inquiry_wait(state: InterviewState) -> str:
    return "wait_answer" if state["inquiry"].get("cancelled") else "inquiry_analyze"


def route_after_judgment(state: InterviewState) -> str:
    """ai-service 3.3 route_after_judgment. 문의 도중 끊기면(cancel) 진행 중이던 질문으로 돌아간다."""
    inq = state["inquiry"]
    if inq.get("cancelled"):
        return "wait_answer"
    if inq["resolved"] is None:  # 지원자가 글을 더 보냈다
        return "inquiry_analyze"
    if inq["resolved"]:
        return "wait_answer" if inq["analysis"]["cause"] == "지원자 측" else "invalidate_and_represent"
    return "inquiry_analyze" if inq["ai_attempt_count"] < MAX_ATTEMPTS else "suspend"
