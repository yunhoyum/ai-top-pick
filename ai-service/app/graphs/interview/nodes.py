"""면접 그래프 노드 (ai-service 3.2, AI Agent 설계서 4.1, RAG 설계서 3장).

- present_question: 질문 음성, 회사 문서 미리 검색(question_context), 질문 주제 판정(뒤에서)
- evaluate_answer: [STT 보정 → 답변 검색 → 내용 점수]와 표정 분석을 동시에, 발화 수치·발화 점수
- wait_expression: 표정 분석이 실패하면 main-api가 다시 분석한 결과를 기다린다 (아키텍처 8)
- score_answer: 표정 점수와 답변 점수
꼬리질문(4단계)과 문의(5단계)는 아직 없다. score_answer 다음은 load_question이다.
"""

import base64
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Callable

from langchain_core.runnables import Runnable
from langgraph.types import interrupt

from app.analysis.expression import calc_expression_score, summarize_expression
from app.analysis.scoring import calc_answer_score
from app.analysis.speech import (
    answer_duration,
    calc_response_delay,
    calc_silence,
    calc_speech_score,
    count_fillers,
    split_segments,
)
from app.chains.answer_content import NO_CLAIM_NOTE, ContentScore, judge_question_topic, score_content
from app.chains.stt_correction import correct_transcript
from app.graphs.interview.state import InterviewState
from app.rag.retriever import Chunk
from app.schemas.internal import Word

log = logging.getLogger(__name__)

Tts = Callable[[str], bytes]  # 질문 글 → wav
Search = Callable[[int, list[str]], list[Chunk]]  # (공고 ID, 검색어) → 회사 문서 청크
Analyze = Callable[[str], list[dict]]  # 영상 경로 → 프레임별 감정
ScoreContent = Callable[..., ContentScore]
JudgeTopic = Callable[..., object]


@dataclass
class Deps:
    tts: Tts
    model: Runnable
    fillers: list[str]
    search: Search
    analyze: Analyze
    score_content: ScoreContent = score_content
    judge_topic: JudgeTopic = judge_question_topic


# 질문 주제 판정은 지원자가 기다리지 않게 뒤에서 돌린다. 결과는 State가 아니라 메모리에 둔다.
# 답변이 왔을 때 결과가 없으면(서버 재시작, 재접속) score_content가 그 자리에서 다시 판정한다 (RAG 설계서 3.1)
_topic_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="topic")
_topics: dict[tuple[int, str], Future] = {}


def _chunks(items: list[dict]) -> list[Chunk]:
    return [Chunk(**c) for c in items]


def make_nodes(deps: Deps) -> dict[str, Callable[[InterviewState], dict]]:
    def load_question(state: InterviewState) -> dict:
        """queue에서 다음 질문을 꺼낸다. 비었으면 current를 None으로 둔다 (종료로 간다)."""
        queue = state.get("queue", [])
        return {"current": queue[0], "queue": queue[1:]} if queue else {"current": None}

    def present_question(state: InterviewState) -> dict:
        """TTS 음성을 만들고 actions에 '제시'를 넣는다 (SYS-011). 질문으로 회사 문서를 미리 검색한다.
        찾은 문서가 있으면 질문 주제 판정을 뒤에서 부른다. 답변 뒤 주장 비교가 다시 쓸 앞부분 계산을 Ollama에 남긴다."""
        current = state["current"]
        audio = base64.b64encode(deps.tts(current["text"])).decode("ascii")
        try:
            context = deps.search(state["posting_id"], [current["text"]])
        except Exception:
            log.exception("질문 %s 회사 문서 검색 실패. 문서 없이 채점한다", current["qkey"])
            context = []
        if context:
            _topics[(state["session_id"], current["qkey"])] = _topic_pool.submit(
                deps.judge_topic, current["text"], context, deps.model
            )
        return {
            "question_context": [asdict(c) for c in context],
            "actions": state.get("actions", []) + [{"type": "present", "question": current, "audio_b64": audio}],
        }

    def wait_answer(state: InterviewState) -> dict:
        """interrupt로 멈춘다. 재개 값(답변 또는 문의)을 받는다.
        재개될 때마다 actions를 비운다. 이번 요청에 돌려줄 행동만 쌓이게 하기 위해서다."""
        value = interrupt({"waiting": "answer", "qkey": state["current"]["qkey"]})
        return {"last_input": value, "actions": []}

    def _content(state: InterviewState, answer_text: str) -> tuple[ContentScore | None, list[dict]]:
        """보정된 답변으로 회사 문서를 검색하고 내용 점수를 낸다. 답변이 없으면 (None, [])."""
        if not answer_text:
            return None, []
        current = state["current"]
        answer_context = deps.search(state["posting_id"], [answer_text])
        future = _topics.pop((state["session_id"], current["qkey"]), None)
        topic = None
        if future is not None:
            try:
                topic = future.result()
            except Exception:
                log.warning("질문 %s 주제 판정 실패. 채점 때 다시 판정한다", current["qkey"])
        score = deps.score_content(
            current["text"], answer_text, _chunks(state.get("question_context", [])), answer_context,
            state["posting"]["job_description"], model=deps.model, topic=topic,
        )
        return score, [asdict(c) for c in answer_context]

    def _expression(video_path: str | None) -> tuple[str | None, dict | None]:
        if not video_path:
            return None, None
        try:
            return summarize_expression(deps.analyze(video_path))
        except Exception as e:
            log.warning("영상 %s 표정 분석 실패: %s", video_path, e)
            return None, None

    def evaluate_answer(state: InterviewState) -> dict:
        """답변을 평가한다 (ai-service 3.2). 표정 분석은 [STT 보정 → 답변 검색 → 내용 점수]와 동시에 돌린다.
        간투사는 보정 전 원문에서 센다 (아키텍처 7-9). 답변 점수는 score_answer에서 낸다."""
        answer = state["last_input"]
        words = [Word(**w) for w in answer.get("words", [])]
        start = answer.get("answer_start_sec", 0.0)
        video_path = answer.get("video_path")
        with ThreadPoolExecutor(max_workers=1) as pool:
            expression = pool.submit(_expression, video_path)
            segments = correct_transcript(deps.model, state["current"]["text"], split_segments(words, start))
            content, answer_context = _content(state, " ".join(s["corrected_text"] for s in segments))
            main_expression, ratio = expression.result()
        filler_count = count_fillers(answer.get("raw_text", ""), fillers=deps.fillers)
        silence = calc_silence(words)
        delay = calc_response_delay(start, words)
        evaluation = {
            "segments": segments,
            "duration_sec": answer_duration(start, words),
            "filler_count": filler_count,
            "silence_sec": silence,
            "response_delay_sec": delay,
            "main_expression": main_expression,
            "expression_ratio": ratio,
            # 답변이 없으면 답변 내용 없음 0점 (루브릭 설계서 3.3)
            "content_score": content.score if content else Decimal("0.00"),
            "content_reason": content.reason if content else NO_CLAIM_NOTE,
            "speech_score": calc_speech_score(filler_count, silence, delay, bool(words)),
            "expression_score": None,
            "answer_score": None,
            "evidence": [asdict(e) for e in content.evidence] if content else [],
            # 영상이 있는데 표정이 없으면 다시 분석한다. 영상이 없으면 다시 분석할 것이 없다
            "needs_expression": bool(video_path) and main_expression is None,
        }
        # interrupt 앞의 노드에서 넣어야 멈춘 상태의 actions에 남는다
        waiting = [{"type": "await_expression", "question": state["current"]}] if evaluation["needs_expression"] else []
        return {
            "answered": state.get("answered", []) + [state["current"]["qkey"]],
            "answer_context": answer_context,
            "last_evaluation": evaluation,
            "actions": state.get("actions", []) + waiting,
        }

    def wait_expression(state: InterviewState) -> dict:
        """actions에 '표정 대기'를 넣고 멈춘다. main-api가 다시 분석한 표정으로 재개한다 (아키텍처 8)."""
        value = interrupt({"waiting": "expression", "qkey": state["current"]["qkey"]})
        evaluation = state["last_evaluation"] | {
            "main_expression": value.get("main_expression"),
            "expression_ratio": value.get("expression_ratio"),
            "needs_expression": False,
        }
        return {"last_evaluation": evaluation, "actions": []}

    def score_answer(state: InterviewState) -> dict:
        """표정 점수와 답변 점수를 낸다 (SYS-007). 표정이 없으면 내용·발화 비율을 늘려 계산한다."""
        e = state["last_evaluation"]
        expression = calc_expression_score(e["expression_ratio"]) if e.get("expression_ratio") else None
        answer = calc_answer_score(
            Decimal(str(e["content_score"])), expression, Decimal(str(e["speech_score"])), state["settings"]["ratios"]
        )
        return {"last_evaluation": e | {"expression_score": expression, "answer_score": answer}}

    def end_interview(state: InterviewState) -> dict:
        """actions에 '종료'를 넣는다 (워크플로우 5-7)."""
        return {"actions": state.get("actions", []) + [{"type": "end"}]}

    return {
        "load_question": load_question,
        "present_question": present_question,
        "wait_answer": wait_answer,
        "evaluate_answer": evaluate_answer,
        "wait_expression": wait_expression,
        "score_answer": score_answer,
        "end_interview": end_interview,
    }
