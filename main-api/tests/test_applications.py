"""지원자 지원 흐름 (APP-005~011)"""

import pytest
from fastapi.testclient import TestClient

from test_postings import PDF, _login, _register, _sql, admin  # noqa: F401  (admin은 fixture)

URL = "/api/postings/{pid}/application"
PROFILE = {"name": "김지원", "phone": "010-1234-5678", "email": "applicant@example.com"}


def _open_posting(admin):
    """서류 접수 중인 공고 (필수 기술 Java 기준 2점 이하 탈락, SQL 기준 없음, 학력 문항 포함, 자소서 주제 2개)"""
    pid = _register(admin)
    _sql("update job_posting set progress_status = '서류 접수 중' where posting_id = :p", p=pid)
    return pid


@pytest.fixture
def pid(admin):
    return _open_posting(admin)


@pytest.fixture
def applicant(client):
    return _login(TestClient(client.app), "지원자")


def _get(c, pid):
    r = c.get(URL.format(pid=pid))
    assert r.status_code == 200, r.text
    return r.json()


def _resume(c, pid, validate=True, **over):
    body = {"profile": PROFILE, "educations": [{"school_name": "한국대", "major": "컴퓨터", "period": "2020.03 ~ 2026.02"}]}
    body.update(over)
    return c.put(URL.format(pid=pid) + f"/resume?validate={str(validate).lower()}", json=body)


def _skills(c, pid, java=3, sql=4, validate=True, **over):
    body = {
        "skills": [{"skill_name": "Java", "score": java}, {"skill_name": "SQL", "score": sql}],
        "cases": [{"skill_name": "Java", "content": "주문 API를 개선했습니다."}],
    }
    body.update(over)
    return c.put(URL.format(pid=pid) + f"/skills?validate={str(validate).lower()}", json=body)


def _essays(c, pid, validate=True, texts=("동기", "장단점")):
    topics = _get(c, pid)["form"]["essay_topics"]
    body = {"essays": [{"topic_id": t["topic_id"], "content": x} for t, x in zip(topics, texts)]}
    return c.put(URL.format(pid=pid) + f"/essays?validate={str(validate).lower()}", json=body)


def _portfolio(c, pid, name="포트.pdf", data=PDF, content_type="application/pdf"):
    return c.post(URL.format(pid=pid) + "/portfolio", files={"file": (name, data, content_type)})


def _fill_all(c, pid, java=3):
    assert _resume(c, pid).status_code == 200
    assert _skills(c, pid, java=java).status_code == 200
    assert _essays(c, pid).status_code == 200
    assert _portfolio(c, pid).status_code == 200


def _submit(c, pid):
    return c.post(URL.format(pid=pid) + "/submit")


# ---------- 접근 권한 ----------
def test_requires_login(client, pid):
    client = TestClient(client.app)  # admin fixture가 client에 로그인해 두었으므로 새 클라이언트를 쓴다
    assert client.get(URL.format(pid=pid)).status_code == 401
    assert client.put(URL.format(pid=pid) + "/resume", json={"profile": {}}).status_code == 401
    assert client.post(URL.format(pid=pid) + "/submit").status_code == 401


def test_admin_previews_but_cannot_save_or_submit(admin, pid):
    d = _get(admin, pid)
    assert d["preview"] is True and d["write_status"] is None
    assert [s["skill_name"] for s in d["skills"]] == ["Java", "SQL"]
    assert admin.put(URL.format(pid=pid) + "/resume", json={"profile": PROFILE}).status_code == 403
    assert admin.post(URL.format(pid=pid) + "/submit").status_code == 403
    assert _sql("select count(*) from application where posting_id = :p", p=pid)[0][0] == 0


def test_unknown_or_draft_posting_is_404(admin, applicant):
    draft = admin.post("/api/admin/postings").json()["posting_id"]
    assert applicant.get(URL.format(pid=draft)).status_code == 404
    assert applicant.get(URL.format(pid=999999999)).status_code == 404


# ---------- 지원서 열기 ----------
def test_get_creates_draft_with_prefilled_profile_and_is_idempotent(applicant, pid):
    d = _get(applicant, pid)
    assert d["preview"] is False and d["write_status"] == "임시 저장"
    assert d["profile"]["name"] == "홍길동" and d["profile"]["email"] and d["profile"]["phone"] is None
    assert d["form"]["has_education"] is True and d["form"]["has_career"] is False and d["form"]["has_project"] is False
    assert [t["topic_name"] for t in d["form"]["essay_topics"]] == ["지원 동기", "성격의 장단점"]
    assert d["skills"] == [
        {"skill_name": "Java", "required": True, "score": None},
        {"skill_name": "SQL", "required": True, "score": None},
    ]
    _get(applicant, pid)
    assert _sql("select count(*) from application where posting_id = :p", p=pid)[0][0] == 1


def test_each_applicant_has_own_application(client, pid):
    a, b = _login(TestClient(client.app), "지원자"), _login(TestClient(client.app), "지원자")
    _get(a, pid)
    assert _resume(a, pid).status_code == 200
    assert _get(b, pid)["profile"]["phone"] is None


def test_closed_posting_cannot_be_applied_to(admin, applicant):
    before = _register(admin)  # 등록 직후 '모집 전'
    r = applicant.get(URL.format(pid=before))
    assert r.status_code == 409 and r.json()["code"] == "APPLICATION_CLOSED"
    assert _sql("select count(*) from application where posting_id = :p", p=before)[0][0] == 0


def test_saving_after_posting_closes_is_rejected(applicant, pid):
    _get(applicant, pid)
    _sql("update job_posting set progress_status = '서류 평가' where posting_id = :p", p=pid)
    r = _resume(applicant, pid)
    assert r.status_code == 409 and r.json()["code"] == "APPLICATION_CLOSED"


# ---------- 이력서 ----------
def test_resume_roundtrip_drops_blank_rows_and_formats_period(applicant, pid):
    _get(applicant, pid)
    r = _resume(
        applicant, pid,
        educations=[
            {"school_name": "한국대", "major": "컴퓨터", "period": "2020.03 ~ 2026.02"},
            {"school_name": "", "major": "", "period": ""},
            {"school_name": "온라인대", "period": "2026.03 ~"},
        ],
    )
    assert r.status_code == 200
    d = _get(applicant, pid)
    assert d["profile"] == PROFILE
    assert [(e["school_name"], e["period"]) for e in d["educations"]] == [
        ("한국대", "2020.03 ~ 2026.02"), ("온라인대", "2026.03 ~"),
    ]


def test_resume_draft_allows_partial_but_next_requires_profile(applicant, pid):
    _get(applicant, pid)
    assert _resume(applicant, pid, validate=False, profile={"name": "김지원"}, educations=[]).status_code == 200
    r = _resume(applicant, pid, profile={"name": "김지원"}, educations=[])
    assert r.status_code == 422 and r.json()["code"] == "APPLICATION_INVALID"


@pytest.mark.parametrize(
    "profile",
    [{**PROFILE, "phone": "12345"}, {**PROFILE, "email": "not-an-email"}, {**PROFILE, "name": " "}],
)
def test_resume_rejects_bad_profile(applicant, pid, profile):
    _get(applicant, pid)
    assert _resume(applicant, pid, profile=profile).status_code == 422


@pytest.mark.parametrize("period", ["2020-03 ~ 2026-02", "2020.13 ~ 2021.01", "2026.02 ~ 2020.03", "abc"])
@pytest.mark.parametrize("validate", [True, False])
def test_resume_rejects_bad_period_even_for_draft(applicant, pid, period, validate):
    _get(applicant, pid)
    r = _resume(applicant, pid, validate=validate, educations=[{"school_name": "한국대", "period": period}])
    assert r.status_code == 422


def test_resume_rejects_section_the_posting_does_not_have(applicant, pid):
    _get(applicant, pid)
    r = _resume(applicant, pid, careers=[{"company_name": "회사"}])
    assert r.status_code == 422


# ---------- 사용기술, 기술 적용 사례 ----------
def test_skills_roundtrip_with_direct_skill_reusing_existing_name(applicant, pid):
    _get(applicant, pid)
    r = _skills(
        applicant, pid,
        skills=[
            {"skill_name": "Java", "score": 3}, {"skill_name": "SQL", "score": 5}, {"skill_name": "docker", "score": 2},
        ],
        cases=[{"skill_name": "docker", "content": "배포 자동화"}],
    )
    assert r.status_code == 200
    d = r.json()
    assert [(s["skill_name"], s["required"], s["score"]) for s in d["skills"]] == [
        ("Java", True, 3), ("SQL", True, 5), ("docker", False, 2),
    ]
    assert d["cases"] == [{"skill_name": "docker", "content": "배포 자동화"}]
    # 같은 이름(대소문자 무시)의 기술은 새로 만들지 않고 다시 쓴다
    other = _login(TestClient(applicant.app), "지원자")
    _get(other, pid)
    assert _skills(other, pid, skills=[{"skill_name": "Docker", "score": 1}, {"skill_name": "Java", "score": 3}, {"skill_name": "SQL", "score": 3}], cases=[{"skill_name": "Docker", "content": "x"}]).status_code == 200
    assert _sql("select count(*) from skill where lower(skill_name) = 'docker'")[0][0] == 1


def test_skills_reject_duplicates_and_unknown_case_skill(applicant, pid):
    _get(applicant, pid)
    dup = [{"skill_name": "Java", "score": 3}, {"skill_name": "java", "score": 4}]
    assert _skills(applicant, pid, skills=dup).status_code == 422
    assert _skills(applicant, pid, cases=[{"skill_name": "Rust", "content": "x"}]).status_code == 422


def test_skills_draft_allows_empty_score_but_next_does_not(applicant, pid):
    _get(applicant, pid)
    partial = {"skills": [{"skill_name": "Java", "score": None}], "cases": []}
    assert _skills(applicant, pid, validate=False, **partial).status_code == 200
    r = _skills(applicant, pid, **partial)
    assert r.status_code == 422 and "점수" in r.json()["message"]


def test_skills_next_requires_a_case(applicant, pid):
    _get(applicant, pid)
    assert _skills(applicant, pid, cases=[]).status_code == 422
    assert _skills(applicant, pid, cases=[{"skill_name": "Java", "content": ""}]).status_code == 422


def test_skills_score_range(applicant, pid):
    _get(applicant, pid)
    assert _skills(applicant, pid, java=6).status_code == 422
    assert _skills(applicant, pid, java=0).status_code == 422


# ---------- 자기소개서 ----------
def test_essays_roundtrip_and_validation(applicant, pid):
    d = _get(applicant, pid)
    t1 = d["form"]["essay_topics"][0]["topic_id"]
    assert _essays(applicant, pid, validate=False, texts=("동기", "")).status_code == 200
    assert _essays(applicant, pid, texts=("동기", "")).status_code == 422
    r = _essays(applicant, pid)
    assert [e["content"] for e in r.json()["essays"]] == ["동기", "장단점"]
    bad = applicant.put(URL.format(pid=pid) + "/essays", json={"essays": [{"topic_id": 999999999, "content": "x"}]})
    assert bad.status_code == 422
    dup = applicant.put(URL.format(pid=pid) + "/essays", json={"essays": [{"topic_id": t1, "content": "x"}, {"topic_id": t1, "content": "y"}]})
    assert dup.status_code == 422


# ---------- 포트폴리오 ----------
def test_portfolio_upload_replace_delete(applicant, pid):
    _get(applicant, pid)
    r = _portfolio(applicant, pid, name="a.pdf")
    assert r.json()["portfolio"] == {"file_name": "a.pdf", "file_size": len(PDF)}
    r = _portfolio(applicant, pid, name="b.pdf")
    assert r.json()["portfolio"]["file_name"] == "b.pdf"
    assert _sql("select count(*) from portfolio p join application a using (application_id) where a.posting_id = :p", p=pid)[0][0] == 1
    assert applicant.delete(URL.format(pid=pid) + "/portfolio").json()["portfolio"] is None


@pytest.mark.parametrize(
    "name,data,ctype",
    [("a.txt", b"hello", "text/plain"), ("a.pdf", b"not a pdf", "application/pdf"), ("a.pdf", PDF, "image/png")],
)
def test_portfolio_rejects_non_pdf(applicant, pid, name, data, ctype):
    _get(applicant, pid)
    assert _portfolio(applicant, pid, name=name, data=data, content_type=ctype).status_code == 422


# ---------- 제출 ----------
def test_submit_lists_incomplete_steps(applicant, pid):
    _get(applicant, pid)
    r = _submit(applicant, pid)
    assert r.status_code == 422
    for step in ("이력서", "사용기술·적용 사례", "자기소개서", "포트폴리오"):
        assert step in r.json()["message"]
    assert _resume(applicant, pid).status_code == 200
    assert "이력서" not in _submit(applicant, pid).json()["message"]


def test_submit_completes_application_and_locks_it(applicant, pid):
    _get(applicant, pid)
    _fill_all(applicant, pid)
    r = _submit(applicant, pid)
    assert r.status_code == 200
    d = r.json()
    assert d["write_status"] == "제출" and d["submitted_at"] is not None
    # 제출 뒤에는 수정, 재제출 모두 막는다
    for resp in (_resume(applicant, pid), _essays(applicant, pid), _portfolio(applicant, pid), _submit(applicant, pid)):
        assert resp.status_code == 409 and resp.json()["code"] == "APPLICATION_SUBMITTED"
    assert applicant.delete(URL.format(pid=pid) + "/portfolio").status_code == 409
    # 접수가 끝난 뒤에도 제출한 지원서는 다시 볼 수 있다
    _sql("update job_posting set progress_status = '서류 평가' where posting_id = :p", p=pid)
    assert _get(applicant, pid)["write_status"] == "제출"


def _shortfall_count(pid):
    return _sql(
        "select count(*) from application_stage s join application a using (application_id) "
        "where a.posting_id = :p and s.stage_type = '서류' and s.result = '필수 기술 미달'", p=pid,
    )[0][0]


@pytest.mark.parametrize("java,shortfall", [(1, 1), (2, 1), (3, 0), (5, 0)])
def test_submit_records_skill_shortfall_when_score_is_at_or_below_cutoff(applicant, pid, java, shortfall):
    _get(applicant, pid)
    _fill_all(applicant, pid, java=java)
    assert _submit(applicant, pid).status_code == 200
    assert _shortfall_count(pid) == shortfall


def test_cutoff_is_not_applied_to_skills_without_one_or_direct_skills(applicant, pid):
    _get(applicant, pid)
    assert _resume(applicant, pid).status_code == 200
    # SQL은 탈락 기준이 없다. 직접 추가한 기술도 기준이 없다
    skills = [{"skill_name": "Java", "score": 3}, {"skill_name": "SQL", "score": 1}, {"skill_name": "Go", "score": 1}]
    assert _skills(applicant, pid, skills=skills).status_code == 200
    assert _essays(applicant, pid).status_code == 200 and _portfolio(applicant, pid).status_code == 200
    assert _submit(applicant, pid).status_code == 200
    assert _shortfall_count(pid) == 0


def test_dashboard_stats_count_submitted_and_shortfall(admin, applicant, pid):
    _get(applicant, pid)
    _fill_all(applicant, pid, java=1)
    _submit(applicant, pid)
    stats = admin.get(f"/api/admin/postings/{pid}/stats").json()
    assert stats["submitted_count"] == 1 and stats["skill_shortfall_count"] == 1
