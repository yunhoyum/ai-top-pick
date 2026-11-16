"""면접 그래프 라우팅 (ai-service 3.3).

문의(route_after_wait의 '문의' → inquiry_wait)는 5단계에서 넣는다.
"""

from app.graphs.interview.nodes import next_job_question, parent_qkey
from app.graphs.interview.state import InterviewState

FOLLOW_UP_MIN_SCORE = 80  # SYS-008
MAX_FOLLOW_UPS = 2  # 부모 질문 하나에 유효 꼬리질문 최대 수 (SYS-008)


def route_after_load(state: InterviewState) -> str:
    """queue가 비었으면 종료, 아니면 질문 제시."""
    return "present_question" if state.get("current") else "end_interview"


def route_after_wait(state: InterviewState) -> str:
    """답변 → evaluate_answer. 문의는 5단계에서 inquiry_wait로 보낸다."""
    return "evaluate_answer"


def route_after_eval(state: InterviewState) -> str:
    """영상이 있는데 표정 분석이 실패했으면 → wait_expression, 아니면 → score_answer (아키텍처 8)."""
    return "wait_expression" if state["last_evaluation"].get("needs_expression") else "score_answer"


def should_follow_up(state: InterviewState) -> bool:
    """다섯 조건이 모두 참일 때 참 (ai-service 3.3, SYS-008).
    ① 꼬리질문 사용 ② 지금 질문이 직무 질문(꼬리질문 포함) ③ 답변 점수 80 이상 ④ 아직 제시하지 않은 직무 질문이 있음
    ⑤ 부모 질문의 유효 꼬리질문 2개 미만. 내용 채점이 끝까지 실패해 답변 점수가 없으면 거짓."""
    current, score = state["current"], state["last_evaluation"].get("answer_score")
    return (
        bool(state["settings"].get("follow_up_enabled"))
        and current.get("kind") in ("AI", "꼬리") and current.get("question_type") == "직무"
        and score is not None and score >= FOLLOW_UP_MIN_SCORE
        and next_job_question(state.get("queue", [])) is not None
        and state.get("follow_up_counts", {}).get(parent_qkey(current), 0) < MAX_FOLLOW_UPS
    )


def route_after_score(state: InterviewState) -> str:
    return "follow_up" if should_follow_up(state) else "load_question"


def route_after_follow_up(state: InterviewState) -> str:
    """꼬리질문을 만들었으면 제시하고, 못 만들었으면 다음 질문을 꺼낸다 (다음 직무 질문은 빼지 않았다)."""
    return "present_question" if state.get("follow_up_created") else "load_question"
