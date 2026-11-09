"""내 지원 현황 (APP-012, APP-017)"""

import pytest
from fastapi.testclient import TestClient

from test_applications import URL, _fill_all, _get, _open_posting, _schedule, _submit, applicant, pid  # noqa: F401
from test_postings import _login, _sql, admin  # noqa: F401  (fixture)


def _mine(c):
    r = c.get("/api/applications")
    assert r.status_code == 200, r.text
    return r.json()


def _one(c, posting_id):
    return next(i for i in _mine(c) if i["posting_id"] == posting_id)


def _submitted(applicant, pid, java=3):
    _get(applicant, pid)
    _fill_all(applicant, pid, java=java)
    assert _submit(applicant, pid).status_code == 200


def _timeline(pid, doc_result, interview_start, interview_end, interview_result):
    """전형 일정을 지금 기준 며칠 전(-)/후(+)로 바꾼다. 서류 마감은 서류 발표 1일 전, 접수 시작은 20일 전"""
    _sql(
        "update job_posting set "
        "doc_start_at = now() + make_interval(days => :dr - 20), doc_end_at = now() + make_interval(days => :dr - 1), "
        "doc_result_at = now() + make_interval(days => :dr), interview_start_at = now() + make_interval(days => :istart), "
        "interview_end_at = now() + make_interval(days => :iend), interview_result_at = now() + make_interval(days => :ires) "
        "where posting_id = :p",
        p=pid, dr=doc_result, istart=interview_start, iend=interview_end, ires=interview_result,
    )


def _stage(pid, stage_type, result):
    aid = _sql("select application_id from application where posting_id = :p", p=pid)[0][0]
    _sql("insert into application_stage (application_id, stage_type, result) values (:a, :t, :r)", a=aid, t=stage_type, r=result)
    return aid


# ---------- 접근 권한 ----------
def test_requires_login_and_is_applicant_only(client, admin):
    assert TestClient(client.app).get("/api/applications").status_code == 401
    assert admin.get("/api/applications").status_code == 403  # 관리자는 쓸 수 없다


def test_new_applicant_has_no_applications(applicant):
    assert _mine(applicant) == []


# ---------- 작성 중 ----------
def test_draft_is_listed_only_while_posting_receives_applications(applicant, pid):
    _get(applicant, pid)
    item = _one(applicant, pid)
    assert item["status"] == "작성 중" and item["write_status"] == "임시 저장"
    assert item["doc_result"] is None and item["can_view_interview_guide"] is False
    _schedule(pid, start="-3 days", end="-1 hour")  # 접수 기간이 끝났다
    assert all(i["posting_id"] != pid for i in _mine(applicant))


# ---------- 서류 전형 ----------
def test_result_is_hidden_until_the_announcement_time(applicant, pid):
    _submitted(applicant, pid)
    _timeline(pid, doc_result=1, interview_start=3, interview_end=5, interview_result=7)
    _stage(pid, "서류", "합격")  # 관리자가 이미 정했어도 발표 전에는 알려 주지 않는다
    item = _one(applicant, pid)
    assert item["status"] == "서류 전형 진행 중" and item["doc_result"] is None
    assert item["can_view_interview_guide"] is False
    assert item["submitted_at"] is not None


def test_announced_without_decision_still_shows_in_progress(applicant, pid):
    _submitted(applicant, pid)
    _timeline(pid, doc_result=-1, interview_start=2, interview_end=4, interview_result=6)
    item = _one(applicant, pid)
    assert item["status"] == "서류 전형 진행 중" and item["doc_result"] is None


def test_doc_pass_before_interview(applicant, pid):
    _submitted(applicant, pid)
    _timeline(pid, doc_result=-1, interview_start=2, interview_end=4, interview_result=6)
    _stage(pid, "서류", "합격")
    item = _one(applicant, pid)
    assert item["status"] == "면접 전형 예정" and item["doc_result"] == "합격"
    assert item["can_view_interview_guide"] is True and item["interview_result"] is None


@pytest.mark.parametrize("result", ["불합격", "필수 기술 미달"])
def test_doc_fail_is_shown_the_same_and_without_reason(applicant, pid, result):
    _submitted(applicant, pid)
    _timeline(pid, doc_result=-1, interview_start=2, interview_end=4, interview_result=6)
    _stage(pid, "서류", result)
    item = _one(applicant, pid)
    assert item["status"] == "전형 종료" and item["doc_result"] == "불합격"
    assert item["can_view_interview_guide"] is False and item["interview_result"] is None
    assert "필수 기술 미달" not in str(item)


def test_skill_shortfall_submitted_through_the_flow_is_hidden_until_announced(applicant, pid):
    _submitted(applicant, pid, java=1)  # Java 기준 2점 이하 → 제출 때 '필수 기술 미달'이 기록된다
    _timeline(pid, doc_result=2, interview_start=4, interview_end=6, interview_result=8)
    assert _one(applicant, pid)["status"] == "서류 전형 진행 중"
    _timeline(pid, doc_result=-1, interview_start=2, interview_end=4, interview_result=6)
    item = _one(applicant, pid)
    assert item["status"] == "전형 종료" and item["doc_result"] == "불합격"


# ---------- 면접 전형 ----------
@pytest.mark.parametrize(
    "timeline,status,guide",
    [
        ((-5, -2, 1, 3), "면접 전형 진행 중", True),
        ((-5, -4, -1, 2), "면접 결과 대기", False),
    ],
)
def test_interview_period_statuses(applicant, pid, timeline, status, guide):
    _submitted(applicant, pid)
    _timeline(pid, *timeline)
    _stage(pid, "서류", "합격")
    item = _one(applicant, pid)
    assert item["status"] == status and item["can_view_interview_guide"] is guide


def test_interview_pass_and_fail_after_announcement(applicant, pid):
    _submitted(applicant, pid)
    _timeline(pid, doc_result=-8, interview_start=-6, interview_end=-4, interview_result=-1)
    _stage(pid, "서류", "합격")
    assert _one(applicant, pid)["status"] == "면접 결과 대기"  # 발표됐지만 아직 결과가 없다
    aid = _stage(pid, "면접", "합격")
    item = _one(applicant, pid)
    assert item["status"] == "면접 전형 완료" and item["interview_result"] == "합격"
    _sql("update application_stage set result = '불합격' where application_id = :a and stage_type = '면접'", a=aid)
    item = _one(applicant, pid)
    assert item["status"] == "전형 종료" and item["interview_result"] == "불합격"


def test_interview_result_is_hidden_before_its_announcement(applicant, pid):
    _submitted(applicant, pid)
    _timeline(pid, doc_result=-8, interview_start=-6, interview_end=-4, interview_result=2)
    _stage(pid, "서류", "합격")
    _stage(pid, "면접", "합격")
    item = _one(applicant, pid)
    assert item["interview_result"] is None and item["status"] == "면접 결과 대기"


def test_interview_taken_flag(applicant, pid):
    _submitted(applicant, pid)
    _timeline(pid, doc_result=-5, interview_start=-2, interview_end=1, interview_result=3)
    aid = _stage(pid, "서류", "합격")
    assert _one(applicant, pid)["interview_taken"] is False
    _sql("insert into interview_session (application_id, status) values (:a, '완료')", a=aid)
    assert _one(applicant, pid)["interview_taken"] is True


# ---------- 본인 것만, 최근 순 ----------
def test_only_own_applications_newest_first(client, admin, applicant, pid):
    second = _open_posting(admin)
    _get(applicant, pid)
    _get(applicant, second)
    other = _login(TestClient(client.app), "지원자")
    _get(other, pid)
    mine = [i["posting_id"] for i in _mine(applicant)]
    assert mine == [second, pid]
    assert [i["posting_id"] for i in _mine(other)] == [pid]
