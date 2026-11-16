"""꼬리질문 서브그래프 (ai-service 3.6, AI Agent 설계서 5장, SYS-008).

  generate_follow_up → validate_follow_up → 통과 → END (꼬리질문 확정)
                                          → 실패 (retry_count < 3) → generate_follow_up (feedback 전달)
  에러(LLM 호출 실패, 출력 형식 오류)는 error_count로 따로 센다. 생성 에러면 다시 생성, 검증 에러면 검증만 다시 한다.
  retry_count ≥ 3 또는 error_count ≥ 3 → fallback_follow_up (지원자 답변만으로) → 실패하면 꼬리질문 없음

검증은 형식(코드, 질문 생성 그래프의 form_problem)을 먼저 보고, 통과하면 독립 LLM 호출로
적절성·배타성·부모 질문 반복을 한 번에 판단한다. 생성 대화 기록은 넘기지 않는다 (AI Agent 설계서 1.3).
회사 문서는 새로 검색하지 않는다. 답변 채점 때 찾은 질문·답변 검색 결과를 쓴다 (아키텍처 10).
"""

import logging
from typing import TypedDict

from langchain_core.runnables import Runnable
from langgraph.graph import END, START, StateGraph

from app.chains.structured import invoke_structured
from app.graphs.question import form_problem, numbered, pick_sentence
from app.prompts import follow_up as prompts
from app.schemas.llm_outputs import BasePick, FollowUpValidation, QuestionOutput

log = logging.getLogger(__name__)

MAX_TRIES = 3  # 검증 실패·에러 각각 (AI Agent 설계서 1.3, 5.2)


class FollowUpState(TypedDict, total=False):
    prev_question: str  # 직전 질문 (꼬리질문의 꼬리질문이면 직전 꼬리질문)
    prev_answer: str  # 직전 답변 (보정문)
    parent_question: str  # 최상위 기본 질문
    contexts: list[str]  # 질문·답변 검색 결과 청크 본문
    compare_questions: list[str]  # 비교 대상 질문 (AI Agent 설계서 2.2)
    follow_up: str | None
    based_on: str  # 꼬리질문이 짚은 답변 문장 (프롬프트 v2)
    valid: bool
    feedback: str
    retry_count: int  # 검증 실패
    error_count: int  # LLM 호출 실패, 출력 형식 오류
    errored: bool  # 방금 노드가 에러로 끝났는지


def build_follow_up_graph(model: Runnable):
    def generate_follow_up(state: FollowUpState) -> dict:
        """T-11 꼬리질문 생성 (프롬프트 v2). ① 더 물을 답변 문장 번호를 고른다(회사 문서 없이) ② 그 문장 하나와
        회사 문서로 쓴다. 답변이 한 문장이면 ①을 부르지 않는다. 번호가 틀리면 ②를 부르지 않고 에러로 센다.
        검증 피드백은 ②에 넘긴다."""
        numbered_answer, sentences = numbered(state["prev_answer"])
        try:
            if len(sentences) == 1:
                sentence = sentences[0]
            else:
                pick = invoke_structured(model, prompts.pick(state["prev_question"], numbered_answer), BasePick)
                sentence = pick_sentence(pick.based_on, sentences)
                if not sentence:
                    raise ValueError(f"답변 문장 번호가 틀렸다: {pick.based_on}")
            out = invoke_structured(model, prompts.write(
                state["prev_question"], sentence, state.get("contexts", []),
                state.get("compare_questions", []), state.get("feedback", ""),
            ), QuestionOutput)
            return {"follow_up": out.question.strip(), "based_on": sentence, "errored": False}
        except Exception as e:
            log.warning("꼬리질문 생성 에러: %s", e)
            return {"follow_up": None, "errored": True, "error_count": state.get("error_count", 0) + 1}

    def validate_follow_up(state: FollowUpState) -> dict:
        """T-12 검증. 형식은 코드가 먼저 본다. 형식이 틀리면 LLM을 부르지 않고 검증 실패로 센다."""
        problem = form_problem(state["follow_up"])
        if problem:
            return {"valid": False, "feedback": problem, "errored": False, "retry_count": state.get("retry_count", 0) + 1}
        try:
            out = invoke_structured(model, prompts.validate(
                state["follow_up"], state["prev_answer"], state["parent_question"], state.get("compare_questions", []),
            ), FollowUpValidation)
        except Exception as e:
            log.warning("꼬리질문 검증 에러: %s", e)
            return {"errored": True, "error_count": state.get("error_count", 0) + 1}
        if out.is_valid:
            return {"valid": True, "errored": False}
        return {"valid": False, "feedback": out.feedback, "errored": False, "retry_count": state.get("retry_count", 0) + 1}

    def fallback_follow_up(state: FollowUpState) -> dict:
        """T-13 지원자 답변만으로 만든다. 실패하거나 형식이 틀리면 꼬리질문 없음."""
        try:
            question = invoke_structured(
                model, prompts.fallback(state["prev_question"], state["prev_answer"]), QuestionOutput
            ).question.strip()
        except Exception as e:
            log.warning("꼬리질문 fallback 실패: %s", e)
            return {"follow_up": None, "valid": False}
        if form_problem(question):
            log.warning("꼬리질문 fallback 형식이 틀려 쓰지 않는다: %s", question)
            return {"follow_up": None, "valid": False}
        return {"follow_up": question, "valid": True}

    def _exhausted(state: FollowUpState) -> bool:
        return state.get("retry_count", 0) >= MAX_TRIES or state.get("error_count", 0) >= MAX_TRIES

    def route_after_generate(state: FollowUpState) -> str:
        if state.get("errored"):
            return "fallback_follow_up" if _exhausted(state) else "generate_follow_up"
        return "validate_follow_up"

    def route_after_validate(state: FollowUpState) -> str:
        if state.get("errored"):  # 생성한 꼬리질문은 그대로 두고 검증만 다시 한다
            return "fallback_follow_up" if _exhausted(state) else "validate_follow_up"
        if state.get("valid"):
            return END
        return "fallback_follow_up" if _exhausted(state) else "generate_follow_up"

    g = StateGraph(FollowUpState)
    g.add_node("generate_follow_up", generate_follow_up)
    g.add_node("validate_follow_up", validate_follow_up)
    g.add_node("fallback_follow_up", fallback_follow_up)
    g.add_edge(START, "generate_follow_up")
    g.add_conditional_edges("generate_follow_up", route_after_generate,
                            ["generate_follow_up", "validate_follow_up", "fallback_follow_up"])
    g.add_conditional_edges("validate_follow_up", route_after_validate,
                            ["generate_follow_up", "validate_follow_up", "fallback_follow_up", END])
    g.add_edge("fallback_follow_up", END)
    return g.compile()


# 생성 3번 + 검증 3번 + 에러 재시도 + fallback을 넉넉히 덮는다 (LangGraph 기본 25)
RECURSION_LIMIT = 30


def make_follow_up(model: Runnable, inputs: FollowUpState) -> str | None:
    """서브그래프를 돌려 확정된 꼬리질문을 돌려준다. 만들지 못하면 None."""
    out = build_follow_up_graph(model).invoke(inputs, {"recursion_limit": RECURSION_LIMIT})
    return out.get("follow_up") if out.get("valid") else None
