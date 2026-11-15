"""면접 그래프 노드 (ai-service 3.2, AI Agent 설계서 4.1).

실시간 면접 1단계: 질문을 꺼내 음성과 함께 제시하고, 답변을 기다렸다가 평가 없이 다음 질문으로 간다.
- present_question의 회사 문서 미리 검색과 질문 주제 판정은 3단계(채점)에서 넣는다.
- evaluate_answer의 STT 보정·표정·발화·내용 채점은 2·3단계에서 넣는다. 지금은 답변 받은 질문만 기록한다.
"""

import base64
from typing import Callable

from langgraph.types import interrupt

from app.graphs.interview.state import InterviewState

Tts = Callable[[str], bytes]  # 질문 글 → wav


def make_nodes(tts: Tts) -> dict[str, Callable[[InterviewState], dict]]:
    def load_question(state: InterviewState) -> dict:
        """queue에서 다음 질문을 꺼낸다. 비었으면 current를 None으로 둔다 (종료로 간다)."""
        queue = state.get("queue", [])
        return {"current": queue[0], "queue": queue[1:]} if queue else {"current": None}

    def present_question(state: InterviewState) -> dict:
        """TTS 음성을 만들고 actions에 '제시'를 넣는다 (SYS-011)."""
        current = state["current"]
        audio = base64.b64encode(tts(current["text"])).decode("ascii")
        return {"actions": state.get("actions", []) + [{"type": "present", "question": current, "audio_b64": audio}]}

    def wait_answer(state: InterviewState) -> dict:
        """interrupt로 멈춘다. 재개 값(답변 또는 문의)을 받는다.
        재개될 때마다 actions를 비운다. 이번 요청에 돌려줄 행동만 쌓이게 하기 위해서다."""
        value = interrupt({"waiting": "answer", "qkey": state["current"]["qkey"]})
        return {"last_input": value, "actions": []}

    def evaluate_answer(state: InterviewState) -> dict:
        """1단계: 평가하지 않는다. 답변 받은 질문만 기록한다 (2·3단계에서 STT 보정·채점을 넣는다)."""
        return {"answered": state.get("answered", []) + [state["current"]["qkey"]], "last_evaluation": None}

    def end_interview(state: InterviewState) -> dict:
        """actions에 '종료'를 넣는다 (워크플로우 5-7)."""
        return {"actions": state.get("actions", []) + [{"type": "end"}]}

    return {
        "load_question": load_question,
        "present_question": present_question,
        "wait_answer": wait_answer,
        "evaluate_answer": evaluate_answer,
        "end_interview": end_interview,
    }
