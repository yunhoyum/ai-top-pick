"""SYS-006 면접 질문 생성 작업: 서류 합격자 확정 → 작업 등록 → 질문 저장. ai-service는 정해 둔 질문을 돌려주는 가짜다.
테스트 공고: 출제 문제 6개, 기업 질문 Q1·Q2, 직무 비율 60 → AI 4개 = 직무 2(2.4 반올림) + 인성 2."""

import pytest
from sqlalchemy.orm import Session

from app.domain.rules import calc_question_counts
from app.services import interview_question_batch as batch
from app.services.progress_batch import get_engine
from app.workers.payloads import build_question_payload
from test_applications import _open_posting
from test_document_report_batch import _apply
from test_evaluation import _close
from test_postings import _sql, admin  # noqa: F401  (admin은 fixture)


@pytest.mark.parametrize(
    "total, company, ratio, expected",
    [
        (6, 2, 60, (2, 2)),  # 4 × 0.6 = 2.4 → 2
        (5, 2, 50, (2, 1)),  # 3 × 0.5 = 1.5 → 2 (반올림)
        (5, 0, 30, (2, 3)),  # 1.5 → 2
        (4, 4, 70, (0, 0)),  # 기업 질문 수 = 출제 문제 개수
        (5, 1, 100, (4, 0)),
        (5, 1, 0, (0, 4)),
    ],
)
def test_calc_question_counts(total, company, ratio, expected):
    assert calc_question_counts(total, company, ratio) == expected


class FakeClient:
    def __init__(self, job=("직무1", "직무2"), personality=("인성1", "인성2"), error=None):
        self.result = {"job": list(job), "personality": list(personality)}
        self.error, self.payloads = error, []

    def generate_questions(self, payload):
        self.payloads.append(payload)
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def pid(admin):
    return _open_posting(admin)


@pytest.fixture
def passed(admin, client, pid):
    """지원자 2명 중 1명을 서류 합격으로 확정한다."""
    winner, loser = _apply(client, pid), _apply(client, pid)
    _close(pid)
    r = admin.post(f"/api/admin/postings/{pid}/stages/document/pass", json={"application_ids": [winner]})
    assert r.status_code == 200, r.text
    return winner, loser


def _jobs(pid):
    return _sql(
        "select job_id, application_id, status from batch_job where posting_id = :p and job_type = '면접 질문 생성'", p=pid
    )


def _questions(aid):
    return _sql(
        "select q.seq, q.question_type, q.content, cq.content, q.is_revealed, q.question_status from interview_question q "
        "left join company_question cq using (company_question_id) where q.application_id = :a order by q.seq",
        a=aid,
    )


def test_confirm_pass_registers_and_sends_job_for_passed_only(pid, passed, sent_jobs):
    winner, _ = passed
    jobs = _jobs(pid)
    assert [(a, s) for _, a, s in jobs] == [(winner, "대기")]
    assert ("면접 질문 생성", jobs[0][0]) in sent_jobs


def test_payload_has_counts_posting_and_documents(pid, passed):
    winner, _ = passed
    with Session(get_engine()) as db:
        payload = build_question_payload(db, winner, 2, 2)
    assert (payload["application_id"], payload["job_count"], payload["personality_count"]) == (winner, 2, 2)
    assert payload["posting"]["posting_id"] == pid
    assert payload["documents"]["skill_cases"] == ["[Java] 주문 API를 개선했습니다."]


def test_generate_saves_job_personality_company_in_order(pid, passed):
    winner, _ = passed
    fake = FakeClient()
    assert batch.generate_interview_questions(_jobs(pid)[0][0], client=fake) == 6

    assert (fake.payloads[0]["job_count"], fake.payloads[0]["personality_count"]) == (2, 2)
    assert _questions(winner) == [
        (1, "직무", "직무1", None, False, "유효"),
        (2, "직무", "직무2", None, False, "유효"),
        (3, "인성", "인성1", None, False, "유효"),
        (4, "인성", "인성2", None, False, "유효"),
        # 기업 질문은 내용을 비우고 company_question을 가리킨다
        (5, None, None, "Q1", False, "유효"),
        (6, None, None, "Q2", False, "유효"),
    ]
    assert _jobs(pid)[0][2] == "완료"


def test_generate_again_replaces_previous_questions(pid, passed):
    winner, _ = passed
    job_id = _jobs(pid)[0][0]
    batch.generate_interview_questions(job_id, client=FakeClient())
    _sql("update batch_job set status = '대기' where job_id = :j", j=job_id)
    batch.generate_interview_questions(job_id, client=FakeClient(job=("새1", "새2")))
    assert [q[2] for q in _questions(winner)][:2] == ["새1", "새2"] and len(_questions(winner)) == 6


def test_no_ai_questions_skips_ai_service(pid, passed):
    winner, _ = passed
    _sql("update job_posting set question_count = 2 where posting_id = :p", p=pid)
    fake = FakeClient()
    assert batch.generate_interview_questions(_jobs(pid)[0][0], client=fake) == 2
    assert fake.payloads == []
    assert [q[3] for q in _questions(winner)] == ["Q1", "Q2"]


def test_count_mismatch_fails_job_and_saves_nothing(pid, passed):
    winner, _ = passed
    with pytest.raises(ValueError):
        batch.generate_interview_questions(_jobs(pid)[0][0], client=FakeClient(job=("직무1",)))
    status, error = _sql("select status, error_message from batch_job where job_id = :j", j=_jobs(pid)[0][0])[0]
    assert status == "실패" and "질문 수" in error
    assert _questions(winner) == []


def test_ai_service_error_fails_job(pid, passed):
    with pytest.raises(RuntimeError):
        batch.generate_interview_questions(_jobs(pid)[0][0], client=FakeClient(error=RuntimeError("ai-service 500")))
    assert _jobs(pid)[0][2] == "실패"
