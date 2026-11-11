"""서류 보고서 작업 (Celery 4장 start_document_reports·generate_document_report, 아키텍처 9.5).
ai-service는 정해 둔 ReportResult를 돌려주는 가짜로 바꾼다."""

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services import document_report_batch as batch
from app.services.progress_batch import advance_posting_progress, get_engine
from app.workers.payloads import build_document_report_payload
from test_applications import _fill_all, _get, _open_posting, _portfolio, _schedule, _submit
from test_postings import _login, _sql, admin  # noqa: F401  (admin은 fixture)


def _text_pdf(text: str) -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text)
    return doc.tobytes()


@pytest.fixture
def pid(admin):
    return _open_posting(admin)


def _apply(client, pid, java=3, submit=True, portfolio=None) -> int:
    """지원자 한 명이 서류를 채우고 제출한다. Java 2점 이하면 필수 기술 미달이다."""
    c = _login(TestClient(client.app), "지원자")
    _get(c, pid)
    _fill_all(c, pid, java=java)
    if portfolio:
        assert _portfolio(c, pid, data=portfolio).status_code == 200
    if submit:
        assert _submit(c, pid).status_code == 200
    return _sql("select max(application_id) from application where posting_id = :p", p=pid)[0][0]


def _jobs(pid):
    return _sql(
        "select application_id, status from batch_job where posting_id = :p and job_type = '서류 보고서' order by application_id",
        p=pid,
    )


# ---------- 요청 본문 ----------


def test_payload_has_posting_criteria_and_selected_documents_only(client, pid):
    aid = _apply(client, pid, portfolio=_text_pdf("Portfolio about search quality"))
    with Session(get_engine()) as db:
        payload = build_document_report_payload(db, aid)

    assert payload["application_id"] == aid
    assert payload["posting"]["posting_id"] == pid and payload["posting"]["job_description"] == "REST API 개발"
    assert payload["posting"]["functional_talent"] == "Spring 기반 REST API 경험"
    assert [(c["criteria_id"], c["name"], c["ratio"]) for c in payload["criteria"]] == [
        (1, "이력서", 30), (2, "기술 적용 사례", 30), (3, "포트폴리오", 20), (4, "자기소개", 20),
    ]
    d = payload["documents"]
    # 이 공고는 기본 문항 중 학력만 골랐다. 경력·프로젝트는 넣지 않는다
    assert d["educations"] == [{"school_name": "한국대", "major": "컴퓨터", "start_date": "2020-03", "end_date": "2026-02"}]
    assert d["careers"] == [] and d["projects"] == []
    assert d["skills"] == [{"skill_name": "Java", "self_score": 3}, {"skill_name": "SQL", "self_score": 4}]
    assert d["skill_cases"] == ["[Java] 주문 API를 개선했습니다."]
    assert d["essays"] == [{"topic": "지원 동기", "content": "동기"}, {"topic": "성격의 장단점", "content": "장단점"}]
    assert "Portfolio about search quality" in d["portfolio_text"]
    assert d["personal"]["name"] == "김지원"


def test_payload_portfolio_without_text_is_none(client, pid):
    aid = _apply(client, pid)  # _fill_all이 올리는 PDF에는 글자가 없다
    with Session(get_engine()) as db:
        assert build_document_report_payload(db, aid)["documents"]["portfolio_text"] is None


# ---------- 작업 등록 ----------


def test_start_registers_submitted_applications_except_skill_shortfall(client, pid, sent_jobs):
    ok = _apply(client, pid, java=3)
    _apply(client, pid, java=2)  # 필수 기술 미달
    _apply(client, pid, submit=False)  # 작성 중
    job_ids = batch.start_document_reports(pid)
    assert _jobs(pid) == [(ok, "대기")]
    # 공고 등록 때 보낸 회사 문서 임베딩 작업은 빼고 본다
    assert [j for j in sent_jobs if j[0] == "서류 보고서"] == [("서류 보고서", job_ids[0])]


def test_doc_deadline_starts_reports(client, pid, sent_jobs):
    ok = _apply(client, pid)
    _schedule(pid, start="-3 days", end="-1 hour")
    assert advance_posting_progress(posting_ids=[pid]) == {"서류 평가": 1}
    assert _jobs(pid) == [(ok, "대기")]
    # 이미 '서류 평가'인 공고는 다시 등록하지 않는다
    sent_jobs.clear()
    assert advance_posting_progress(posting_ids=[pid]) == {}
    assert sent_jobs == []


# ---------- 결과 저장 ----------


def _result(summary="요약이다.", score="64.50"):
    return {
        "scores": [
            {"criteria_id": 1, "score": "70.00", "evidence": "이력서 이유", "evidence_sentences": []},
            {
                "criteria_id": 2, "score": score, "evidence": "사례 이유",
                "evidence_sentences": [
                    {"source_type": "프로젝트 문서", "source_id": None, "chunk_id": 11, "sentence": "문서 문장"},
                    {"source_type": "기능적 인재상", "source_id": None, "chunk_id": None, "sentence": "Spring 기반 REST API 경험"},
                ],
            },
            {"criteria_id": 3, "score": "0.00", "evidence": "포트폴리오 이유", "evidence_sentences": []},
            {"criteria_id": 4, "score": "0.00", "evidence": "자기소개 이유", "evidence_sentences": []},
        ],
        "fits": [{"talent_content": "Spring 기반 REST API 경험", "evidence": "기술 적용 사례: 주문 API를 개선했다"}],
        "points": [{"point_type": "확인 필요", "criteria_id": 2, "content": "결과 수치가 없다."}],
        "summary": summary,
    }


class FakeClient:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.payloads = result, error, []

    def create_document_report(self, payload):
        self.payloads.append(payload)
        if self.error:
            raise self.error
        return self.result


def _report_rows(aid):
    report = _sql(
        "select r.report_id, r.ai_summary, s.result from stage_report r join application_stage s using (application_stage_id) "
        "where s.application_id = :a and s.stage_type = '서류'", a=aid,
    )
    if not report:
        return None
    rid, summary, stage_result = report[0]
    return {
        "summary": summary,
        "stage_result": stage_result,
        "scores": _sql("select criteria_id, score::text, evidence from report_score where report_id = :r order by criteria_id", r=rid),
        "evidence": _sql(
            "select criteria_id, seq, source_type, chunk_id, sentence from evidence_sentence where report_id = :r order by criteria_id, seq",
            r=rid,
        ),
        "fits": _sql("select talent_content, evidence from report_fit where report_id = :r", r=rid),
        "points": _sql("select criteria_id, point_type, content from report_point where report_id = :r", r=rid),
    }


def _job_id(pid, aid):
    return _sql("select job_id from batch_job where posting_id = :p and application_id = :a", p=pid, a=aid)[0][0]


def test_generate_saves_report_and_creates_document_stage(client, pid):
    aid = _apply(client, pid)
    batch.start_document_reports(pid)
    fake = FakeClient(_result())
    report_id = batch.generate_document_report(_job_id(pid, aid), client=fake)

    assert report_id is not None and fake.payloads[0]["application_id"] == aid
    rows = _report_rows(aid)
    assert rows["summary"] == "요약이다." and rows["stage_result"] is None  # 합격·불합격은 관리자가 정한다
    assert [s[:2] for s in rows["scores"]] == [(1, "70.00"), (2, "64.50"), (3, "0.00"), (4, "0.00")]
    assert rows["evidence"] == [
        (2, 1, "프로젝트 문서", 11, "문서 문장"),
        (2, 2, "기능적 인재상", None, "Spring 기반 REST API 경험"),
    ]
    assert rows["fits"] == [("Spring 기반 REST API 경험", "기술 적용 사례: 주문 API를 개선했다")]
    assert rows["points"] == [(2, "확인 필요", "결과 수치가 없다.")]
    assert _jobs(pid) == [(aid, "완료")]


def test_generate_again_replaces_previous_report(client, pid):
    aid = _apply(client, pid)
    batch.start_document_reports(pid)
    batch.generate_document_report(_job_id(pid, aid), client=FakeClient(_result()))
    batch.start_document_reports(pid)  # 같은 작업을 다시 '대기'로
    batch.generate_document_report(_job_id(pid, aid), client=FakeClient(_result("새 요약", "80.00")))

    rows = _report_rows(aid)
    assert rows["summary"] == "새 요약" and rows["scores"][1][1] == "80.00"
    assert len(rows["evidence"]) == 2 and len(rows["fits"]) == 1 and len(rows["points"]) == 1
    assert _sql("select count(*) from stage_report r join application_stage s using (application_stage_id) "
                "where s.application_id = :a", a=aid)[0][0] == 1


def test_generate_failure_marks_job_failed_and_saves_nothing(client, pid):
    aid = _apply(client, pid)
    batch.start_document_reports(pid)
    with pytest.raises(RuntimeError):
        batch.generate_document_report(_job_id(pid, aid), client=FakeClient(error=RuntimeError("ai-service 502")))
    status, error = _sql("select status, error_message from batch_job where job_id = :j", j=_job_id(pid, aid))[0]
    assert status == "실패" and "ai-service 502" in error
    assert _report_rows(aid) is None


def test_generate_skips_job_that_is_not_pending(client, pid):
    aid = _apply(client, pid)
    batch.start_document_reports(pid)
    job_id = _job_id(pid, aid)
    batch.generate_document_report(job_id, client=FakeClient(_result()))
    fake = FakeClient(_result())
    assert batch.generate_document_report(job_id, client=fake) is None  # 이미 '완료'
    assert fake.payloads == []
