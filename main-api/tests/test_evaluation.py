"""서류 전형 평가 화면 API: 지원자 순위(화면 17), 결과 보고서(화면 18), 관리자 의견.
보고서는 서류 보고서 작업에 가짜 ai-service를 넣어 만든다 (test_document_report_batch)."""

import pytest
from fastapi.testclient import TestClient

from app.services import document_report_batch as batch
from test_applications import _open_posting
from test_document_report_batch import FakeClient, _apply, _job_id, _result
from test_postings import PDF, _login, _sql, admin  # noqa: F401  (admin은 fixture)

NO_FIT = "서류에서 이 인재상과 맞는 경험을 찾지 못했다."


@pytest.fixture
def pid(admin):
    return _open_posting(admin)


def _close(pid):
    _sql("update job_posting set progress_status = '서류 평가' where posting_id = :p", p=pid)


def _report_for(pid, aid, score="64.50", summary="요약이다."):
    result = _result(summary, score)
    result["fits"].append({"talent_content": "끝까지 파고드는 태도", "evidence": NO_FIT})
    result["points"].append({"point_type": "강점", "criteria_id": 1, "content": "회사 자료와 맞는 일: 'REST API'"})
    batch.generate_document_report(_job_id(pid, aid), client=FakeClient(result))


@pytest.fixture
def ranked(client, pid):
    """지원자 4명: 보고서 2명(총점 45.0, 40.4), 보고서 작업 대기 1명, 필수 기술 미달 1명. 서류 평가비율 30·30·20·20."""
    low = _apply(client, pid)
    high = _apply(client, pid)
    pending = _apply(client, pid)
    shortfall = _apply(client, pid, java=2)
    batch.start_document_reports(pid)
    _report_for(pid, low)  # 70×0.3 + 64.5×0.3 = 21 + 19.35 = 40.35 → 40.4
    _report_for(pid, high, score="80.00")  # 21 + 24 = 45.0
    _close(pid)
    return {"low": low, "high": high, "pending": pending, "shortfall": shortfall}


def _ranking(c, pid):
    return c.get(f"/api/admin/postings/{pid}/stages/document/ranking")


def _report(c, aid):
    return c.get(f"/api/admin/applications/{aid}/stages/document/report")


def test_ranking_orders_by_total_and_puts_pending_last(admin, pid, ranked):
    r = _ranking(admin, pid)
    assert r.status_code == 200, r.text
    data = r.json()
    assert [c["name"] for c in data["criteria"]] == ["이력서", "기술 적용 사례", "포트폴리오", "자기소개"]
    assert [(row["application_id"], row["rank"], row["total"], row["report_status"]) for row in data["rows"]] == [
        (ranked["high"], 1, "45.0", "완료"),
        (ranked["low"], 2, "40.4", "완료"),
        (ranked["pending"], None, None, "대기"),
    ]
    assert [s["weighted"] for s in data["rows"][1]["scores"]] == ["21.0", "19.4", "0.0", "0.0"]
    assert data["summary"] == {"target_count": 3, "shortfall_count": 1, "average": "42.7", "opinion_count": 0}


def test_ranking_before_doc_deadline_is_409(admin, pid):
    r = _ranking(admin, pid)
    assert r.status_code == 409 and r.json()["code"] == "STAGE_NOT_CLOSED"


def test_other_admin_cannot_see_ranking_or_report(client, admin, pid, ranked):
    other = _login(TestClient(client.app))
    assert _ranking(other, pid).status_code == 404
    r = _report(other, ranked["high"])
    assert r.status_code == 404 and r.json()["code"] == "APPLICATION_NOT_FOUND"


def test_report_has_scores_fits_points_and_rank(admin, pid, ranked):
    r = _report(admin, ranked["low"])
    assert r.status_code == 200, r.text
    data = r.json()
    assert (data["total"], data["rank"], data["ranked_count"], data["summary"]) == ("40.4", 2, 2, "요약이다.")
    assert [(s["name"], s["ratio"], s["score"], s["weighted"]) for s in data["scores"]] == [
        ("이력서", 30, "70.00", "21.0"), ("기술 적용 사례", 30, "64.50", "19.4"),
        ("포트폴리오", 20, "0.00", "0.0"), ("자기소개", 20, "0.00", "0.0"),
    ]
    assert data["scores"][0]["evidence"] == "이력서 이유"
    # 공고의 기능적 인재상은 'Spring 기반 REST API 경험'이다. 인재상 종류는 공고 전문에서 찾는다
    assert [(f["talent_content"], f["kind"], f["found"]) for f in data["fits"]] == [
        ("Spring 기반 REST API 경험", "기능적", True),
        ("끝까지 파고드는 태도", "비기능적", False),
    ]
    assert data["strengths"] == [{"criteria_name": "이력서", "content": "회사 자료와 맞는 일: 'REST API'"}]
    assert data["checks"] == [{"criteria_name": "기술 적용 사례", "content": "결과 수치가 없다."}]
    assert data["opinion"] is None


def test_report_not_ready_is_404(admin, pid, ranked):
    r = _report(admin, ranked["pending"])
    assert r.status_code == 404 and r.json()["code"] == "REPORT_NOT_FOUND"


def test_opinion_is_saved_and_shown_in_ranking_and_report(admin, pid, ranked):
    url = f"/api/admin/applications/{ranked['low']}/stages/document/opinion"
    r = admin.put(url, json={"opinion": "  협업 경험을 면접에서 묻는다.  "})
    assert r.status_code == 200 and r.json() == {"opinion": "협업 경험을 면접에서 묻는다."}
    assert _report(admin, ranked["low"]).json()["opinion"] == "협업 경험을 면접에서 묻는다."
    ranking = _ranking(admin, pid).json()
    assert ranking["summary"]["opinion_count"] == 1
    assert [row["has_opinion"] for row in ranking["rows"]] == [False, True, False]
    # 비우면 지운다
    assert admin.put(url, json={"opinion": " "}).json() == {"opinion": None}
    assert _ranking(admin, pid).json()["summary"]["opinion_count"] == 0


# ---------- 화면 20 합격자 선정 ----------


def _pass(c, pid, ids):
    return c.post(f"/api/admin/postings/{pid}/stages/document/pass", json={"application_ids": ids})


def _stage(aid, stage):
    rows = _sql("select result from application_stage where application_id = :a and stage_type = :s", a=aid, s=stage)
    return rows[0][0] if rows else "없음"


def test_confirm_pass_marks_selected_pass_and_others_fail_once(admin, pid, ranked):
    before = _ranking(admin, pid).json()
    assert before["confirmed"] is False and [r["result"] for r in before["rows"]] == [None, None, None]

    r = _pass(admin, pid, [ranked["high"]])
    assert r.status_code == 200 and r.json() == {"passed": 1, "failed": 2}
    assert (_stage(ranked["high"], "서류"), _stage(ranked["low"], "서류"), _stage(ranked["pending"], "서류")) == ("합격", "불합격", "불합격")
    assert _stage(ranked["shortfall"], "서류") == "필수 기술 미달"  # 그대로 둔다
    # 합격자만 면접 전형 행이 생긴다 (결과는 비어 있다)
    assert (_stage(ranked["high"], "면접"), _stage(ranked["low"], "면접")) == (None, "없음")

    after = _ranking(admin, pid).json()
    assert after["confirmed"] is True and [r["result"] for r in after["rows"]] == ["합격", "불합격", "불합격"]
    again = _pass(admin, pid, [ranked["low"]])
    assert again.status_code == 409 and again.json()["code"] == "STAGE_ALREADY_CONFIRMED"


def test_confirm_pass_rejects_non_targets_and_empty_selection(admin, pid, ranked):
    r = _pass(admin, pid, [ranked["shortfall"]])
    assert r.status_code == 422 and r.json()["code"] == "APPLICATION_INVALID"
    assert _pass(admin, pid, []).status_code == 422
    assert _ranking(admin, pid).json()["confirmed"] is False


def test_ranking_rows_carry_opinion_text(admin, pid, ranked):
    admin.put(f"/api/admin/applications/{ranked['low']}/stages/document/opinion", json={"opinion": "협업 확인"})
    rows = _ranking(admin, pid).json()["rows"]
    assert [r["opinion"] for r in rows] == [None, "협업 확인", None]


# ---------- 화면 19 지원자 자료 원본 ----------


def test_source_documents_show_submitted_resume_essays_and_portfolio(admin, pid, ranked):
    r = admin.get(f"/api/admin/applications/{ranked['low']}/documents")
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["name"], d["phone"], d["email"]) == ("김지원", "010-1234-5678", "applicant@example.com")
    assert d["educations"] == [{"school_name": "한국대", "major": "컴퓨터", "period": "2020.03 ~ 2026.02"}]
    assert d["skills"] == [{"skill_name": "Java", "score": 3}, {"skill_name": "SQL", "score": 4}]
    assert d["cases"] == [{"skill_name": "Java", "content": "주문 API를 개선했습니다."}]
    assert d["essays"] == [{"topic": "지원 동기", "content": "동기"}, {"topic": "성격의 장단점", "content": "장단점"}]
    assert d["portfolio"]["file_name"] == "포트.pdf"


def test_portfolio_file_is_served_inline(admin, pid, ranked):
    r = admin.get(f"/api/admin/applications/{ranked['low']}/portfolio/file")
    assert r.status_code == 200 and r.content == PDF
    assert r.headers["content-type"] == "application/pdf" and r.headers["content-disposition"].startswith("inline")


def test_other_admin_cannot_see_source_documents(client, pid, ranked):
    other = _login(TestClient(client.app))
    assert other.get(f"/api/admin/applications/{ranked['low']}/documents").status_code == 404
    assert other.get(f"/api/admin/applications/{ranked['low']}/portfolio/file").status_code == 404
