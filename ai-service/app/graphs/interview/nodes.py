"""면접 그래프 노드 (ai-service 3.2, AI Agent 설계서 4.1).

실시간 면접 1·2단계: 질문을 꺼내 음성과 함께 제시하고, 답변을 기다렸다가 STT 보정과 발화 수치를 내고 다음 질문으로 간다.
- present_question의 회사 문서 미리 검색과 질문 주제 판정은 3단계(채점)에서 넣는다.
- evaluate_answer의 표정 분석·내용 채점·답변 점수는 3단계에서 넣는다.
"""

import base64
from typing import Callable

from langchain_core.runnables import Runnable
from langgraph.types import interrupt

from app.analysis.speech import answer_duration, calc_response_delay, calc_silence, count_fillers, split_segments
from app.chains.stt_correction import correct_transcript
from app.graphs.interview.state import InterviewState
from app.schemas.internal import Word

Tts = Callable[[str], bytes]  # 질문 글 → wav


def make_nodes(tts: Tts, model: Runnable, fillers: list[str]) -> dict[str, Callable[[InterviewState], dict]]:
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
        """답변을 평가한다 (ai-service 3.2). 2단계: STT 원문을 구간으로 나눠 보정하고(T-31), 발화 수치를 낸다.
        간투사는 보정 전 원문에서 센다 (아키텍처 7-9). 표정·내용·답변 점수는 3단계에서 넣는다."""
        answer = state["last_input"]
        words = [Word(**w) for w in answer.get("words", [])]
        start = answer.get("answer_start_sec", 0.0)
        segments = correct_transcript(model, state["current"]["text"], split_segments(words, start))
        evaluation = {
            "segments": segments,
            "duration_sec": answer_duration(start, words),
            "filler_count": count_fillers(answer.get("raw_text", ""), fillers),
            "silence_sec": calc_silence(words),
            "response_delay_sec": calc_response_delay(start, words),
        }
        return {"answered": state.get("answered", []) + [state["current"]["qkey"]], "last_evaluation": evaluation}

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
