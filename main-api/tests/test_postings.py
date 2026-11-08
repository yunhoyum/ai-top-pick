import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import get_settings

PASSWORD = "password1"
PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"

FULL = {
    "position_name": "백엔드 개발자 (신입)",
    "job_category": "백엔드",
    "employment_type": "정규직",
    "job_description": "REST API 개발",
    "doc_start_at": "2026-10-27T00:00:00+09:00",
    "doc_end_at": "2026-11-05T23:59:00+09:00",
    "doc_result_at": "2026-11-10T10:00:00+09:00",
    "interview_start_at": "2026-11-12T09:00:00+09:00",
    "interview_end_at": "2026-11-16T18:00:00+09:00",
    "interview_result_at": "2026-11-20T10:00:00+09:00",
    "functional_talent": "Spring 기반 REST API 경험",
    "nonfunctional_talent": "끝까지 파고드는 태도",
}


def _login(client, role="관리자"):
    email = f"{uuid.uuid4().hex}@example.com"
    client.post(
        "/api/auth/signup",
        json={
            "role": role,
            "name": "홍길동",
            "email": email,
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "company_name": "테스트회사" if role == "관리자" else None,
        },
    )
    r = client.post("/api/auth/login", json={"role": role, "email": email, "password": PASSWORD})
    assert r.status_code == 200
    return client


@pytest.fixture
def admin(client):
    return _login(client)


@pytest.fixture
def posting_id(admin):
    return admin.post("/api/admin/postings").json()["posting_id"]


def _sql(statement, **params):
    engine = create_engine(get_settings().sqlalchemy_url)
    with engine.begin() as conn:
        result = conn.execute(text(statement), params)
        rows = result.fetchall() if result.returns_rows else None
    engine.dispose()
    return rows


# ---------- 접근 권한 ----------
def test_requires_login(client):
    assert client.post("/api/admin/postings").status_code == 401


def test_applicant_is_forbidden(client):
    _login(client, "지원자")
    r = client.post("/api/admin/postings")
    assert r.status_code == 403 and r.json()["code"] == "FORBIDDEN"


# ---------- 생성·조회 ----------
def test_create_draft(admin, posting_id):
    r = admin.get(f"/api/admin/postings/{posting_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["write_status"] == "임시 저장" and body["progress_status"] == "모집 전"
    assert body["documents"] == [] and body["position_name"] is None


def test_other_admin_gets_404(admin, posting_id):
    with TestClient(admin.app) as other:
        _login(other)
        assert other.get(f"/api/admin/postings/{posting_id}").status_code == 404
        assert other.put(f"/api/admin/postings/{posting_id}/info", json=FULL).status_code == 404
        assert other.post(
            f"/api/admin/postings/{posting_id}/documents",
            files={"file": ("a.pdf", PDF, "application/pdf")},
        ).status_code == 404


# ---------- 공고 정보 저장 ----------
def test_draft_save_allows_partial(admin, posting_id):
    r = admin.put(
        f"/api/admin/postings/{posting_id}/info?validate=false",
        json={"position_name": "  백엔드  ", "job_category": ""},
    )
    assert r.status_code == 200
    body = admin.get(f"/api/admin/postings/{posting_id}").json()
    assert body["position_name"] == "백엔드"  # 앞뒤 공백 제거
    assert body["job_category"] is None  # 빈 문자열은 없는 값


def test_next_requires_all_fields(admin, posting_id):
    r = admin.put(f"/api/admin/postings/{posting_id}/info", json={"position_name": "백엔드"})
    assert r.status_code == 422 and r.json()["code"] == "POSTING_INVALID"
    assert "직무 분류" in r.json()["message"] and "포지션명" not in r.json()["message"]


def test_full_save_roundtrip(admin, posting_id):
    r = admin.put(f"/api/admin/postings/{posting_id}/info", json=FULL)
    assert r.status_code == 200
    body = r.json()
    assert body["employment_type"] == "정규직" and body["job_category"] == "백엔드"
    # 같은 시각(+09:00)으로 저장되고 되돌려진다
    from datetime import datetime

    assert datetime.fromisoformat(body["doc_end_at"]) == datetime.fromisoformat(FULL["doc_end_at"])


@pytest.mark.parametrize(
    "over",
    [
        {"doc_end_at": "2026-10-26T00:00:00+09:00"},  # 마감이 시작보다 앞
        {"doc_result_at": "2026-11-05T23:59:00+09:00"},  # 발표가 마감과 같은 시각
        {"interview_start_at": "2026-11-10T10:00:00+09:00"},  # 면접 시작이 서류 발표와 같은 시각
        {"interview_result_at": "2026-11-16T18:00:00+09:00"},  # 면접 발표가 면접 마감과 같은 시각
    ],
)
@pytest.mark.parametrize("validate", ["true", "false"])
def test_invalid_schedule_is_422_even_for_draft(admin, posting_id, over, validate):
    r = admin.put(f"/api/admin/postings/{posting_id}/info?validate={validate}", json={**FULL, **over})
    assert r.status_code == 422 and r.json()["code"] == "POSTING_INVALID"  # DB 제약에 걸려 500이 되면 안 된다


def test_invalid_input_values(admin, posting_id):
    for bad in [{"employment_type": "인턴"}, {"doc_start_at": "2026-10-27T00:00:00"}]:  # 허용 안 되는 값, 시간대 없음
        assert admin.put(f"/api/admin/postings/{posting_id}/info?validate=false", json=bad).status_code == 422


def test_published_posting_is_not_editable(admin, posting_id):
    _sql(
        "update job_posting set write_status='등록 완료', progress_status='서류 접수 중' where posting_id=:p",
        p=posting_id,
    )
    r = admin.put(f"/api/admin/postings/{posting_id}/info", json=FULL)
    assert r.status_code == 409 and r.json()["code"] == "POSTING_NOT_EDITABLE"
    r = admin.post(
        f"/api/admin/postings/{posting_id}/documents", files={"file": ("a.pdf", PDF, "application/pdf")}
    )
    assert r.status_code == 409


# ---------- 프로젝트 문서 ----------
def _upload(admin, posting_id, name="소개.pdf", data=PDF, content_type="application/pdf"):
    return admin.post(
        f"/api/admin/postings/{posting_id}/documents", files={"file": (name, data, content_type)}
    )


def test_upload_multiple_pdfs(admin, posting_id):
    first, second = _upload(admin, posting_id, "소개.pdf"), _upload(admin, posting_id, "설명.pdf")
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["file_name"] == "소개.pdf" and first.json()["upload_status"] == "등록 완료"
    assert first.json()["file_size"] == len(PDF)
    # 파일은 사용자 파일명이 아니라 document_id로 저장된다
    saved = Path(get_settings().STORAGE_ROOT) / f"postings/{posting_id}/documents/{first.json()['document_id']}.pdf"
    assert saved.read_bytes() == PDF
    names = [d["file_name"] for d in admin.get(f"/api/admin/postings/{posting_id}").json()["documents"]]
    assert names == ["소개.pdf", "설명.pdf"]


@pytest.mark.parametrize(
    "name,data,content_type",
    [
        ("a.txt", PDF, "application/pdf"),  # 확장자
        ("a.pdf", PDF, "text/plain"),  # MIME
        ("a.pdf", b"hello, not a pdf", "application/pdf"),  # 시작 바이트
    ],
)
def test_upload_rejects_non_pdf(admin, posting_id, name, data, content_type):
    r = _upload(admin, posting_id, name, data, content_type)
    assert r.status_code == 422 and r.json()["code"] == "FILE_INVALID"
    assert admin.get(f"/api/admin/postings/{posting_id}").json()["documents"] == []  # 행도 남지 않는다


def test_upload_rejects_oversize(admin, posting_id, monkeypatch):
    monkeypatch.setattr(get_settings(), "MAX_PDF_MB", 0)
    r = _upload(admin, posting_id)
    assert r.status_code == 413 and r.json()["code"] == "FILE_TOO_LARGE"


def test_delete_document_removes_row_and_file(admin, posting_id):
    doc = _upload(admin, posting_id).json()
    path = Path(get_settings().STORAGE_ROOT) / f"postings/{posting_id}/documents/{doc['document_id']}.pdf"
    assert path.exists()
    assert admin.delete(f"/api/admin/postings/{posting_id}/documents/{doc['document_id']}").status_code == 204
    assert not path.exists()
    assert admin.get(f"/api/admin/postings/{posting_id}").json()["documents"] == []
    r = admin.delete(f"/api/admin/postings/{posting_id}/documents/{doc['document_id']}")
    assert r.status_code == 404 and r.json()["code"] == "DOCUMENT_NOT_FOUND"
