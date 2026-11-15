"""면접 그래프 라우팅 (ai-service 3.3).

문의(route_after_wait의 '문의' → inquiry_wait)는 5단계, 꼬리질문(route_after_score)은 4단계에서 넣는다.
"""

from app.graphs.interview.state import InterviewState


def route_after_load(state: InterviewState) -> str:
    """queue가 비었으면 종료, 아니면 질문 제시."""
    return "present_question" if state.get("current") else "end_interview"


def route_after_wait(state: InterviewState) -> str:
    """답변 → evaluate_answer. 문의는 5단계에서 inquiry_wait로 보낸다."""
    return "evaluate_answer"


def route_after_eval(state: InterviewState) -> str:
    """영상이 있는데 표정 분석이 실패했으면 → wait_expression, 아니면 → score_answer (아키텍처 8)."""
    return "wait_expression" if state["last_evaluation"].get("needs_expression") else "score_answer"
