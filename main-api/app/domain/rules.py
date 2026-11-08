"""DB와 무관한 계산·검증 규칙 (순수 함수)."""

from datetime import datetime
from typing import Protocol

from app.domain.enums import PostingWriteStatus, ProgressStatus


class _Schedule(Protocol):
    doc_start_at: datetime | None
    doc_end_at: datetime | None
    doc_result_at: datetime | None
    interview_start_at: datetime | None
    interview_end_at: datetime | None
    interview_result_at: datetime | None


# (앞 일정, 뒤 일정, 같은 시각 허용 여부) — ADM-004 일정 순서
_ORDER = [
    ("doc_start_at", "doc_end_at", True, "서류 접수 마감은 서류 접수 시작과 같거나 이후여야 합니다."),
    ("doc_end_at", "doc_result_at", False, "서류 합격자 발표는 서류 접수 마감 이후여야 합니다."),
    ("doc_result_at", "interview_start_at", False, "면접 시작은 서류 합격자 발표 이후여야 합니다."),
    ("interview_start_at", "interview_end_at", True, "면접 마감은 면접 시작과 같거나 이후여야 합니다."),
    ("interview_end_at", "interview_result_at", False, "면접 합격자 발표는 면접 마감 이후여야 합니다."),
]


def validate_schedule(s: _Schedule) -> list[str]:
    """ADM-004 일정 순서(서류 시작 ≤ 서류 마감 < 서류 발표 < 면접 시작 ≤ 면접 마감 < 면접 발표)를
    어긴 항목의 메시지 목록. 둘 다 입력된 이웃 항목만 비교한다."""
    errors = []
    for before, after, allow_equal, message in _ORDER:
        a, b = getattr(s, before), getattr(s, after)
        if a is None or b is None:
            continue
        if a > b or (a == b and not allow_equal):
            errors.append(message)
    return errors


def can_edit_posting(posting) -> bool:
    """ADM-014~020 작성 상태가 '임시 저장'이거나 진행 상태가 '모집 전'이면 수정할 수 있다."""
    return (
        posting.write_status == PostingWriteStatus.DRAFT.value
        or posting.progress_status == ProgressStatus.BEFORE_RECRUIT.value
    )
