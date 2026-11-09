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


# 진행 상태의 순서. 상태는 이 순서에서 앞으로만 간다
PROGRESS_ORDER = [p.value for p in ProgressStatus]


def expected_progress(s: _Schedule, now: datetime) -> str:
    """일정으로 본 지금의 진행 상태. 각 일정 시각이 되면(그 시각 포함) 다음 상태로 넘어간다.
    일정이 비어 있으면 그 시각의 전환은 일어나지 않는다."""
    transitions = [
        (s.interview_result_at, ProgressStatus.CLOSED),
        (s.interview_end_at, ProgressStatus.INTERVIEW_EVALUATION),
        (s.interview_start_at, ProgressStatus.INTERVIEW_ONGOING),
        (s.doc_end_at, ProgressStatus.DOC_EVALUATION),
        (s.doc_start_at, ProgressStatus.DOC_RECEIVING),
    ]
    for at, status in transitions:
        if at is not None and now >= at:
            return status.value
    return ProgressStatus.BEFORE_RECRUIT.value


def is_accepting_applications(s: _Schedule, now: datetime) -> bool:
    """서류 접수 시작 일시 이상, 마감 일시 미만일 때만 지원서를 받는다. 마감 시각 정각부터는 받지 않는다.
    진행 상태(배치가 1분 단위로 바꾼다)와 상관없이 시각으로 직접 판단한다."""
    return s.doc_start_at is not None and s.doc_end_at is not None and s.doc_start_at <= now < s.doc_end_at


def can_edit_posting(posting) -> bool:
    """ADM-014~020 작성 상태가 '임시 저장'이거나 진행 상태가 '모집 전'이면 수정할 수 있다."""
    return (
        posting.write_status == PostingWriteStatus.DRAFT.value
        or posting.progress_status == ProgressStatus.BEFORE_RECRUIT.value
    )
