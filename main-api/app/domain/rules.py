"""DB와 무관한 계산·검증 규칙 (순수 함수)."""

from datetime import datetime
from typing import Protocol

from app.domain.enums import ItemName, PostingWriteStatus, ProgressStatus


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


def resume_description(selected_item_names: list[str]) -> str:
    """ADM-007 이력서 평가 대상 설명. 인적사항과 필수 기술은 항상 평가하고,
    학력·경력·프로젝트는 공고가 선택한 것만 평가한다. 기술 적용 사례는 별도 평가 항목이다."""
    optional = [ItemName.EDUCATION, ItemName.CAREER, ItemName.PROJECT]
    chosen = [i.value for i in optional if i.value in selected_item_names]
    return "·".join([ItemName.PROFILE.value, "필수 기술", *chosen])


def can_edit_posting(posting) -> bool:
    """ADM-014~020 작성 상태가 '임시 저장'이거나 진행 상태가 '모집 전'이면 수정할 수 있다."""
    return (
        posting.write_status == PostingWriteStatus.DRAFT.value
        or posting.progress_status == ProgressStatus.BEFORE_RECRUIT.value
    )
