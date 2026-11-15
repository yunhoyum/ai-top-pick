"""면접 그래프 State (ai-service 3.1, AI Agent 설계서 4.3).

질문은 QuestionItem을 dict로 둔다. 체크포인트에 그대로 저장된다.
실시간 면접 1단계에서 채우는 필드는 session_id, posting_id, settings, queue, current, answered, posting, documents,
actions다. 나머지는 뒤 단계(채점·꼬리질문·문의)에서 채운다.
"""

from typing import TypedDict


class InterviewState(TypedDict, total=False):
    session_id: int  # thread_id는 session-{session_id} (3.5)
    posting_id: int  # RAG 검색 범위
    settings: dict  # InterviewSettings: 꼬리질문 사용 여부, 생각·답변 시간, 면접 항목 비율
    queue: list[dict]  # 아직 제시하지 않은 질문 (직무 → 인성 → 기업)
    current: dict | None  # 지금 질문. queue가 비면 None
    answered: list[str]  # 유효 답변을 받은 질문 qkey
    follow_up_counts: dict[str, int]  # 부모 질문 qkey → 유효 꼬리질문 수 (4단계)
    posting: dict  # PostingBrief. 직무 설명·인재상 전문
    documents: dict  # ApplicantDocuments. AI 직무 질문 대체 때 검색어 (5단계)
    question_context: list  # 질문 출제 때 미리 검색한 회사 문서 (3단계)
    answer_context: list  # 보정된 답변으로 검색한 회사 문서 (3단계)
    last_evaluation: dict | None  # 마지막 답변 평가 결과 (3단계)
    inquiry: dict | None  # 문의 중 대화, 판단 결과, ai_attempt_count (5단계)
    pending_answer: dict | None  # 문의 중 들어온 답변 (보류. 유지보수 때 설계)
    last_input: dict | None  # wait_answer가 받은 재개 값 (답변 또는 문의)
    actions: list[dict]  # main-api에 돌려줄 행동 목록. 요청마다 새로 쌓는다
