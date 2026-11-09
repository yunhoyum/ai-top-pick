"""공고 진행 상태 배치 (일정이 지나면 진행 상태를 앞으로 올린다)"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine

from app.core.config import get_settings
from app.domain.rules import expected_progress, is_accepting_applications
from app.services.progress_batch import advance_posting_progress
from app.workers import tasks  # noqa: F401  (작업 등록)
from app.workers.celery_app import celery_app
from test_postings import _register, _sql, admin  # noqa: F401  (admin은 fixture)

T0 = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)


class Sched:
    """순수 함수 테스트용 일정. 접수 11/1 12:00~11/5 12:00, 서류 발표 11/6, 면접 11/8~11/10, 면접 발표 11/12"""

    doc_start_at = T0
    doc_end_at = T0 + timedelta(days=4)
    doc_result_at = T0 + timedelta(days=5)
    interview_start_at = T0 + timedelta(days=7)
    interview_end_at = T0 + timedelta(days=9)
    interview_result_at = T0 + timedelta(days=11)


# ---------- 순수 규칙 ----------
@pytest.mark.parametrize(
    "offset,expected",
    [
        (timedelta(seconds=-1), "모집 전"),
        (timedelta(0), "서류 접수 중"),  # 시작 시각 정각부터
        (timedelta(days=3), "서류 접수 중"),
        (timedelta(days=4) - timedelta(seconds=1), "서류 접수 중"),
        (timedelta(days=4), "서류 평가"),  # 마감 시각 정각부터
        (timedelta(days=6), "서류 평가"),  # 서류 발표 일시는 상태를 바꾸지 않는다
        (timedelta(days=7), "면접 진행"),
        (timedelta(days=9), "면접 평가"),
        (timedelta(days=10), "면접 평가"),
        (timedelta(days=11), "마감"),
        (timedelta(days=99), "마감"),
    ],
)
def test_expected_progress(offset, expected):
    assert expected_progress(Sched, T0 + offset) == expected


def test_expected_progress_with_missing_schedule_stays_before_recruit():
    class Empty:
        doc_start_at = doc_end_at = doc_result_at = interview_start_at = interview_end_at = interview_result_at = None

    assert expected_progress(Empty, T0) == "모집 전"


@pytest.mark.parametrize(
    "offset,accepting",
    [
        (timedelta(seconds=-1), False),
        (timedelta(0), True),
        (timedelta(days=4) - timedelta(seconds=1), True),
        (timedelta(days=4), False),  # 12:00:00 마감이면 12:00:00부터 받지 않는다
        (timedelta(days=4, seconds=1), False),
    ],
)
def test_is_accepting_applications_is_strict_at_the_deadline(offset, accepting):
    assert is_accepting_applications(Sched, T0 + offset) is accepting


# ---------- 배치 ----------
@pytest.fixture
def engine():
    e = create_engine(get_settings().sqlalchemy_url)
    yield e
    e.dispose()


def _status(pid):
    return _sql("select progress_status from job_posting where posting_id = :p", p=pid)[0][0]


def _set_schedule(pid, base: datetime):
    """base를 접수 시작으로 해서 Sched와 같은 간격의 일정을 넣는다"""
    _sql(
        "update job_posting set doc_start_at = :a, doc_end_at = :b, doc_result_at = :c, "
        "interview_start_at = :d, interview_end_at = :e, interview_result_at = :f where posting_id = :p",
        p=pid, a=base, b=base + timedelta(days=4), c=base + timedelta(days=5),
        d=base + timedelta(days=7), e=base + timedelta(days=9), f=base + timedelta(days=11),
    )


def test_batch_moves_status_forward_as_time_passes(admin, engine):
    pid = _register(admin)
    base = datetime(2030, 1, 1, tzinfo=timezone.utc)
    _set_schedule(pid, base)
    run = lambda days: advance_posting_progress(engine, now=base + timedelta(days=days), posting_ids=[pid])
    assert run(-1) == {} and _status(pid) == "모집 전"
    assert run(0) == {"서류 접수 중": 1} and _status(pid) == "서류 접수 중"
    assert run(1) == {}  # 같은 상태면 그대로
    assert run(4) == {"서류 평가": 1} and _status(pid) == "서류 평가"
    assert run(7) == {"면접 진행": 1} and _status(pid) == "면접 진행"
    assert run(9) == {"면접 평가": 1} and _status(pid) == "면접 평가"
    assert run(11) == {"마감": 1} and _status(pid) == "마감"
    assert run(99) == {}  # 마감은 더 바뀌지 않는다


def test_batch_skips_steps_when_it_was_stopped_for_a_while(admin, engine):
    pid = _register(admin)
    base = datetime(2030, 1, 1, tzinfo=timezone.utc)
    _set_schedule(pid, base)
    assert advance_posting_progress(engine, now=base + timedelta(days=8), posting_ids=[pid]) == {"면접 진행": 1}
    assert _status(pid) == "면접 진행"


def test_batch_never_moves_status_backwards(admin, engine):
    pid = _register(admin)
    base = datetime(2030, 1, 1, tzinfo=timezone.utc)
    _set_schedule(pid, base)
    _sql("update job_posting set progress_status = '면접 진행' where posting_id = :p", p=pid)
    assert advance_posting_progress(engine, now=base + timedelta(days=1), posting_ids=[pid]) == {}
    assert _status(pid) == "면접 진행"


def test_batch_ignores_postings_still_being_written(admin, engine):
    pid = admin.post("/api/admin/postings").json()["posting_id"]  # 임시 저장
    _sql("update job_posting set doc_start_at = '2000-01-01', doc_end_at = '2000-01-02' where posting_id = :p", p=pid)
    assert advance_posting_progress(engine, now=datetime(2030, 1, 1, tzinfo=timezone.utc), posting_ids=[pid]) == {}
    assert _status(pid) == "모집 전"


def test_batch_leaves_postings_outside_the_given_ids_alone(admin, engine):
    pid, other = _register(admin), _register(admin)
    base = datetime(2030, 1, 1, tzinfo=timezone.utc)
    for p in (pid, other):
        _set_schedule(p, base)
    advance_posting_progress(engine, now=base + timedelta(days=1), posting_ids=[pid])
    assert _status(pid) == "서류 접수 중" and _status(other) == "모집 전"


def test_status_change_makes_posting_uneditable_automatically(admin, engine):
    pid = _register(admin)
    base = datetime(2030, 1, 1, tzinfo=timezone.utc)
    _set_schedule(pid, base)
    advance_posting_progress(engine, now=base, posting_ids=[pid])
    r = admin.delete(f"/api/admin/postings/{pid}")
    assert r.status_code == 409 and r.json()["code"] == "POSTING_NOT_EDITABLE"


# ---------- celery 설정 ----------
def test_beat_runs_the_progress_task_every_minute():
    entry = celery_app.conf.beat_schedule["advance-posting-progress"]
    assert entry["task"] == "posting.advance_progress" and entry["schedule"] == 60.0
    assert "posting.advance_progress" in celery_app.tasks
