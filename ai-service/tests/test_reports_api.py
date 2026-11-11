"""서류 보고서 내부 API 테스트. 체인은 정해 둔 결과를 돌려주는 가짜로 바꾼다 (체인은 test_document_report.py)."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api import reports
from app.chains.document_report import DocumentReport, Fit, ItemScore, Point, SourceSentence
from app.chains.structured import StructuredOutputError
from app.core.config import get_settings
from app.main import app

CRITERIA = [
    {"criteria_id": 1, "name": "이력서", "description": None, "ratio": 25},
    {"criteria_id": 2, "name": "기술 적용 사례", "description": None, "ratio": 30},
    {"criteria_id": 3, "name": "포트폴리오", "description": None, "ratio": 25},
    {"criteria_id": 4, "name": "자기소개", "description": None, "ratio": 20},
]
BODY = {
    "application_id": 7,
    "posting": {
        "posting_id": 1, "position_name": "AI 엔지니어", "job_description": "RAG를 개발한다.",
        "functional_talent": "검색을 개선하는 사람", "nonfunctional_talent": "정직한 사람",
    },
    "criteria": CRITERIA,
    "documents": {
        "personal": {"name": "홍길동"}, "skills": [], "educations": [], "careers": [], "projects": [],
        "skill_cases": ["사례"], "essays": [], "portfolio_text": None,
    },
}
PROJECT = SourceSentence("1-1", "PG 승인 응답이 5초 안에 오지 않으면 확인 중으로 둔다.", "프로젝트 문서", 101, 11)
TALENT = SourceSentence("기-1", "검색을 개선하는 사람", "기능적 인재상")


def _item(name, score, evidence=()):
    return ItemScore(name, Decimal(score), f"{name} 이유", list(evidence), {}, {})


REPORT = DocumentReport(
    items=[_item("이력서", "70.00"), _item("기술 적용 사례", "64.50", [PROJECT, TALENT]),
           _item("포트폴리오", "0.00"), _item("자기소개", "0.00")],
    fits=[Fit("검색을 개선하는 사람", "기술 적용 사례: 확인 중으로 두었다")],
    points=[Point("확인 필요", "기술 적용 사례", "결과 수치가 없다.")],
    summary="요약이다.",
    llm_output={},
)


@pytest.fixture
def client(monkeypatch):
    calls = []

    def fake(posting, documents):
        calls.append((posting, documents))
        return REPORT

    monkeypatch.setattr(reports, "build_document_report", fake)
    c = TestClient(app)
    c.calls = calls
    return c


def _post(client, body=BODY, token=None):
    token = get_settings().INTERNAL_TOKEN if token is None else token
    return client.post("/internal/reports/document", json=body, headers={"X-Internal-Token": token} if token else {})


def test_requires_internal_token(client):
    assert _post(client, token="").status_code == 401
    assert _post(client, token="wrong").status_code == 401
    assert client.calls == []


def test_returns_report_result_with_criteria_ids(client):
    r = _post(client)
    assert r.status_code == 200
    data = r.json()
    assert [(s["criteria_id"], s["score"], s["evidence"]) for s in data["scores"]] == [
        (1, "70.00", "이력서 이유"), (2, "64.50", "기술 적용 사례 이유"), (3, "0.00", "포트폴리오 이유"), (4, "0.00", "자기소개 이유"),
    ]
    assert data["scores"][1]["evidence_sentences"] == [
        {"source_type": "프로젝트 문서", "source_id": 101, "chunk_id": 11, "sentence": PROJECT.text},
        {"source_type": "기능적 인재상", "source_id": None, "chunk_id": None, "sentence": "검색을 개선하는 사람"},
    ]
    assert data["fits"] == [{"talent_content": "검색을 개선하는 사람", "evidence": "기술 적용 사례: 확인 중으로 두었다"}]
    assert data["points"] == [{"point_type": "확인 필요", "criteria_id": 2, "content": "결과 수치가 없다."}]
    assert data["summary"] == "요약이다."
    posting, documents = client.calls[0]
    assert posting.posting_id == 1 and documents.skill_cases == ["사례"]


def test_missing_document_criteria_is_rejected_before_llm(client):
    r = _post(client, {**BODY, "criteria": CRITERIA[:3]})
    assert r.status_code == 422 and "자기소개" in r.json()["detail"]
    assert client.calls == []


def test_llm_format_failure_is_502(monkeypatch):
    def fail(posting, documents):
        raise StructuredOutputError("형식 검증 실패")

    monkeypatch.setattr(reports, "build_document_report", fail)
    r = _post(TestClient(app))
    assert r.status_code == 502 and "형식 검증 실패" in r.json()["detail"]
