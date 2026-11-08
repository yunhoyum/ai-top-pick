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


# ---------- 서류 작성 문항 (화면 05, ADM-006) ----------
def _items(admin, pid):
    return admin.get(f"/api/admin/postings/{pid}/doc-items").json()


def _selected(data):
    return sorted(i["item_id"] for i in data["basic_items"] if i["selected"])


DOC_ITEMS = {
    "basic_item_ids": [1, 2, 5],
    "skills": [{"skill_name": "Java", "cutoff_score": 2}, {"skill_name": "SQL", "cutoff_score": None}],
    "essay_topics": ["지원 동기", "성격의 장단점"],
}


def test_doc_items_requires_login(client):
    assert client.get("/api/admin/postings/1/doc-items").status_code == 401


def test_doc_items_initial_has_only_required_selected(admin, posting_id):
    data = _items(admin, posting_id)
    # 필수 문항이 앞에 온다
    assert [i["item_name"] for i in data["basic_items"]] == ["인적사항", "기술 적용 사례", "학력", "경력", "프로젝트"]
    assert _selected(data) == [1, 5]
    assert data["skills"] == [] and data["essay_topics"] == []


def test_doc_items_round_trip(admin, posting_id):
    r = admin.put(f"/api/admin/postings/{posting_id}/doc-items", json=DOC_ITEMS)
    assert r.status_code == 200
    data = _items(admin, posting_id)
    assert _selected(data) == [1, 2, 5]
    assert data["skills"] == DOC_ITEMS["skills"]
    assert data["essay_topics"] == ["지원 동기", "성격의 장단점"]


def test_doc_items_save_replaces_previous(admin, posting_id):
    admin.put(f"/api/admin/postings/{posting_id}/doc-items", json=DOC_ITEMS)
    admin.put(
        f"/api/admin/postings/{posting_id}/doc-items",
        json={"basic_item_ids": [3], "skills": [{"skill_name": "Spring", "cutoff_score": 3}], "essay_topics": ["지원 동기"]},
    )
    data = _items(admin, posting_id)
    assert _selected(data) == [1, 3, 5]
    assert [s["skill_name"] for s in data["skills"]] == ["Spring"]
    assert data["essay_topics"] == ["지원 동기"]


def test_doc_items_required_items_cannot_be_removed(admin, posting_id):
    admin.put(f"/api/admin/postings/{posting_id}/doc-items?validate=false", json={"basic_item_ids": []})
    assert _selected(_items(admin, posting_id)) == [1, 5]


def test_doc_items_unknown_basic_item(admin, posting_id):
    r = admin.put(f"/api/admin/postings/{posting_id}/doc-items", json={"basic_item_ids": [99]})
    assert r.status_code == 422 and r.json()["code"] == "POSTING_INVALID"


def test_doc_items_next_requires_skill_and_topic(admin, posting_id):
    r = admin.put(f"/api/admin/postings/{posting_id}/doc-items", json={})
    assert r.status_code == 422
    assert "필수 기술" in r.json()["message"] and "자기소개서 주제" in r.json()["message"]
    only_skill = {"skills": [{"skill_name": "Java"}]}
    r = admin.put(f"/api/admin/postings/{posting_id}/doc-items", json=only_skill)
    assert r.status_code == 422 and "자기소개서 주제" in r.json()["message"] and "필수 기술" not in r.json()["message"]


def test_doc_items_draft_allows_empty(admin, posting_id):
    r = admin.put(f"/api/admin/postings/{posting_id}/doc-items?validate=false", json={})
    assert r.status_code == 200


def test_doc_items_blank_rows_are_dropped(admin, posting_id):
    admin.put(
        f"/api/admin/postings/{posting_id}/doc-items?validate=false",
        json={"skills": [{"skill_name": "  "}, {"skill_name": " Java "}], "essay_topics": ["", " 지원 동기 "]},
    )
    data = _items(admin, posting_id)
    assert [s["skill_name"] for s in data["skills"]] == ["Java"]
    assert data["essay_topics"] == ["지원 동기"]


@pytest.mark.parametrize("validate", ["true", "false"])
def test_doc_items_duplicate_skill_rejected(admin, posting_id, validate):
    body = {"skills": [{"skill_name": "Java"}, {"skill_name": "java"}], "essay_topics": ["지원 동기"]}
    r = admin.put(f"/api/admin/postings/{posting_id}/doc-items?validate={validate}", json=body)
    assert r.status_code == 422 and "두 번" in r.json()["message"]


@pytest.mark.parametrize("score", [0, 5])
def test_doc_items_cutoff_out_of_range(admin, posting_id, score):
    r = admin.put(
        f"/api/admin/postings/{posting_id}/doc-items",
        json={"skills": [{"skill_name": "Java", "cutoff_score": score}], "essay_topics": ["a"]},
    )
    assert r.status_code == 422


def test_doc_items_skill_is_shared_between_postings(admin, posting_id):
    other = admin.post("/api/admin/postings").json()["posting_id"]
    name = f"Skill-{uuid.uuid4().hex[:8]}"
    for pid, written in ((posting_id, name), (other, name.upper())):
        admin.put(
            f"/api/admin/postings/{pid}/doc-items?validate=false", json={"skills": [{"skill_name": written}]}
        )
    count = _sql("select count(*) from skill where lower(skill_name) = :n", n=name.lower())[0][0]
    assert count == 1


def test_doc_items_other_admin_gets_404(admin, posting_id, client):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as other:
        _login(other)
        assert other.get(f"/api/admin/postings/{posting_id}/doc-items").status_code == 404
        assert other.put(f"/api/admin/postings/{posting_id}/doc-items", json=DOC_ITEMS).status_code == 404


def test_doc_items_not_editable(admin, posting_id):
    _sql(
        "update job_posting set write_status = '등록 완료', progress_status = '서류 접수 중' where posting_id = :p",
        p=posting_id,
    )
    r = admin.put(f"/api/admin/postings/{posting_id}/doc-items", json=DOC_ITEMS)
    assert r.status_code == 409 and r.json()["code"] == "POSTING_NOT_EDITABLE"


# ---------- 서류 평가기준 (화면 06, ADM-007) ----------
def _criteria(admin, pid):
    return admin.get(f"/api/admin/postings/{pid}/doc-criteria").json()["criteria"]


def _put_ratios(admin, pid, values, validate="true"):
    """values: 서류 항목 1~4의 비율 목록 (None은 미입력)"""
    body = {"ratios": [{"criteria_id": i, "ratio": v} for i, v in enumerate(values, start=1)]}
    return admin.put(f"/api/admin/postings/{pid}/doc-criteria?validate={validate}", json=body)


def test_doc_criteria_requires_login(client):
    assert client.get("/api/admin/postings/1/doc-criteria").status_code == 401


def test_doc_criteria_initial_is_blank(admin, posting_id):
    criteria = _criteria(admin, posting_id)
    assert [c["criteria_name"] for c in criteria] == ["이력서", "기술 적용 사례", "포트폴리오", "자기소개"]
    assert all(c["ratio"] is None for c in criteria)
    assert [c["description"] for c in criteria][1:] == [
        "기술을 실제로 적용한 경험",
        "제출한 PDF 포트폴리오",
        "자기소개서 주제별 답변",
    ]


def test_doc_criteria_resume_description_follows_basic_items(admin, posting_id):
    assert _criteria(admin, posting_id)[0]["description"] == "인적사항·필수 기술"
    admin.put(
        f"/api/admin/postings/{posting_id}/doc-items?validate=false", json={"basic_item_ids": [4, 2]}
    )
    assert _criteria(admin, posting_id)[0]["description"] == "인적사항·필수 기술·학력·프로젝트"
    admin.put(
        f"/api/admin/postings/{posting_id}/doc-items?validate=false", json={"basic_item_ids": [2, 3, 4]}
    )
    assert _criteria(admin, posting_id)[0]["description"] == "인적사항·필수 기술·학력·경력·프로젝트"


def test_doc_criteria_round_trip_allows_zero(admin, posting_id):
    assert _put_ratios(admin, posting_id, [40, 30, 0, 30]).status_code == 200
    assert [c["ratio"] for c in _criteria(admin, posting_id)] == [40, 30, 0, 30]


def test_doc_criteria_next_requires_sum_100(admin, posting_id):
    r = _put_ratios(admin, posting_id, [30, 30, 25, 10])
    assert r.status_code == 422 and r.json()["code"] == "POSTING_INVALID"
    assert "합은 100" in r.json()["message"] and "현재 95" in r.json()["message"]
    r = _put_ratios(admin, posting_id, [30, 30, 25, 20])
    assert r.status_code == 422 and "100을 넘을 수 없습니다" in r.json()["message"] and "현재 105" in r.json()["message"]


def test_doc_criteria_next_requires_all_items(admin, posting_id):
    r = _put_ratios(admin, posting_id, [50, 50, None, None])
    assert r.status_code == 422 and "모든 항목" in r.json()["message"]


def test_doc_criteria_draft_allows_partial_and_under_100(admin, posting_id):
    assert _put_ratios(admin, posting_id, [30, None, None, 60], validate="false").status_code == 200
    assert [c["ratio"] for c in _criteria(admin, posting_id)] == [30, None, None, 60]


def test_doc_criteria_draft_rejects_sum_over_100(admin, posting_id):
    _put_ratios(admin, posting_id, [10, 20, 30, 40])
    r = _put_ratios(admin, posting_id, [30, None, None, 90], validate="false")
    assert r.status_code == 422 and "100을 넘을 수 없습니다" in r.json()["message"] and "현재 120" in r.json()["message"]
    # 거절된 저장은 이전 값을 바꾸지 않는다
    assert [c["ratio"] for c in _criteria(admin, posting_id)] == [10, 20, 30, 40]


@pytest.mark.parametrize("value", [-1, 101])
def test_doc_criteria_ratio_out_of_range(admin, posting_id, value):
    assert _put_ratios(admin, posting_id, [value, 0, 0, 0], validate="false").status_code == 422


def test_doc_criteria_rejects_unknown_and_duplicate_items(admin, posting_id):
    url = f"/api/admin/postings/{posting_id}/doc-criteria?validate=false"
    # 5번은 면접 항목이다
    assert admin.put(url, json={"ratios": [{"criteria_id": 5, "ratio": 10}]}).status_code == 422
    dup = {"ratios": [{"criteria_id": 1, "ratio": 10}, {"criteria_id": 1, "ratio": 20}]}
    assert admin.put(url, json=dup).status_code == 422


def test_doc_criteria_save_keeps_interview_ratios(admin, posting_id):
    _sql("insert into posting_eval_ratio (posting_id, criteria_id, ratio) values (:p, 5, 60)", p=posting_id)
    _put_ratios(admin, posting_id, [25, 25, 25, 25])
    _put_ratios(admin, posting_id, [10, 20, 30, 40])
    rows = _sql("select criteria_id, ratio from posting_eval_ratio where posting_id = :p order by 1", p=posting_id)
    assert [tuple(r) for r in rows] == [(1, 10), (2, 20), (3, 30), (4, 40), (5, 60)]


def test_doc_criteria_other_admin_gets_404(admin, posting_id):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as other:
        _login(other)
        assert other.get(f"/api/admin/postings/{posting_id}/doc-criteria").status_code == 404
        assert _put_ratios(other, posting_id, [25, 25, 25, 25]).status_code == 404


def test_doc_criteria_not_editable(admin, posting_id):
    _sql(
        "update job_posting set write_status = '등록 완료', progress_status = '서류 접수 중' where posting_id = :p",
        p=posting_id,
    )
    r = _put_ratios(admin, posting_id, [25, 25, 25, 25])
    assert r.status_code == 409 and r.json()["code"] == "POSTING_NOT_EDITABLE"

# ---------- 면접 평가기준 (화면 07, ADM-008) ----------
def _interview(admin, pid):
    return admin.get(f"/api/admin/postings/{pid}/interview-criteria").json()


def _put_interview(admin, pid, ratios=(50, 30, 20), settings=None, validate="true"):
    """ratios: 면접 항목 5~7의 비율 목록 (None은 미입력)"""
    body = {"ratios": [{"criteria_id": i, "ratio": v} for i, v in enumerate(ratios, start=5)]}
    body.update(
        settings
        if settings is not None
        else {"question_count": 6, "follow_up_enabled": True, "think_time_sec": 30, "answer_time_sec": 90}
    )
    return admin.put(f"/api/admin/postings/{pid}/interview-criteria?validate={validate}", json=body)


def test_interview_criteria_requires_login(client):
    assert client.get("/api/admin/postings/1/interview-criteria").status_code == 401


def test_interview_criteria_initial_is_blank(admin, posting_id):
    data = _interview(admin, posting_id)
    assert [c["criteria_name"] for c in data["criteria"]] == ["내용", "언어", "비언어"]
    assert [c["description"] for c in data["criteria"]] == ["답변 내용", "언어적 측면", "비언어적 측면 (얼굴 표정·감정)"]
    assert all(c["ratio"] is None for c in data["criteria"])
    assert [data[k] for k in ("question_count", "follow_up_enabled", "think_time_sec", "answer_time_sec")] == [None] * 4


def test_interview_criteria_round_trip(admin, posting_id):
    assert _put_interview(admin, posting_id).status_code == 200
    data = _interview(admin, posting_id)
    assert [c["ratio"] for c in data["criteria"]] == [50, 30, 20]
    assert (data["question_count"], data["follow_up_enabled"], data["think_time_sec"], data["answer_time_sec"]) == (6, True, 30, 90)
    # 꼬리질문 '사용 안 함'(false)은 아직 고르지 않은 상태(null)와 다르다
    _put_interview(admin, posting_id, settings={"question_count": 6, "follow_up_enabled": False, "think_time_sec": 0, "answer_time_sec": 5})
    data = _interview(admin, posting_id)
    assert data["follow_up_enabled"] is False and data["think_time_sec"] == 0 and data["answer_time_sec"] == 5


def test_interview_settings_have_no_range_limit(admin, posting_id):
    big = {"question_count": 500, "follow_up_enabled": True, "think_time_sec": 100000, "answer_time_sec": 3}
    assert _put_interview(admin, posting_id, settings=big).status_code == 200
    assert _interview(admin, posting_id)["think_time_sec"] == 100000


def test_interview_settings_reject_negative(admin, posting_id):
    r = _put_interview(admin, posting_id, settings={"question_count": -1})
    assert r.status_code == 422


@pytest.mark.parametrize("validate", ["true", "false"])
def test_interview_nonverbal_cannot_be_zero(admin, posting_id, validate):
    r = _put_interview(admin, posting_id, ratios=(60, 40, 0), validate=validate)
    assert r.status_code == 422 and "비언어 비율은 1% 이상" in r.json()["message"]


def test_interview_content_and_language_may_be_zero(admin, posting_id):
    assert _put_interview(admin, posting_id, ratios=(0, 50, 50)).status_code == 200
    assert _put_interview(admin, posting_id, ratios=(50, 0, 50)).status_code == 200


def test_interview_next_requires_sum_100(admin, posting_id):
    r = _put_interview(admin, posting_id, ratios=(50, 30, 10))
    assert r.status_code == 422 and "합은 100" in r.json()["message"] and "현재 90" in r.json()["message"]


def test_interview_sum_over_100_is_rejected_even_for_draft(admin, posting_id):
    _put_interview(admin, posting_id)
    r = _put_interview(admin, posting_id, ratios=(60, 50, 10), validate="false")
    assert r.status_code == 422 and "100을 넘을 수 없습니다" in r.json()["message"]
    assert [c["ratio"] for c in _interview(admin, posting_id)["criteria"]] == [50, 30, 20]


def test_interview_next_requires_all_values(admin, posting_id):
    r = _put_interview(admin, posting_id, ratios=(50, 50, None), settings={"question_count": 6})
    assert r.status_code == 422
    message = r.json()["message"]
    assert "모든 항목의 비율" in message
    for label in ("꼬리질문", "생각 시간", "답변 시간"):
        assert label in message
    assert "출제 문제 개수" not in message.split("입력해 주세요:")[1]


def test_interview_draft_allows_partial(admin, posting_id):
    r = _put_interview(admin, posting_id, ratios=(30, None, None), settings={"think_time_sec": 20}, validate="false")
    assert r.status_code == 200
    data = _interview(admin, posting_id)
    assert [c["ratio"] for c in data["criteria"]] == [30, None, None] and data["think_time_sec"] == 20


def test_interview_rejects_document_criteria_ids(admin, posting_id):
    body = {"ratios": [{"criteria_id": 1, "ratio": 10}]}
    r = admin.put(f"/api/admin/postings/{posting_id}/interview-criteria?validate=false", json=body)
    assert r.status_code == 422


def test_interview_save_keeps_document_ratios(admin, posting_id):
    _put_ratios(admin, posting_id, [25, 25, 25, 25])
    _put_interview(admin, posting_id)
    _put_interview(admin, posting_id, ratios=(40, 40, 20))
    rows = _sql("select criteria_id, ratio from posting_eval_ratio where posting_id = :p order by 1", p=posting_id)
    assert [tuple(r) for r in rows] == [(1, 25), (2, 25), (3, 25), (4, 25), (5, 40), (6, 40), (7, 20)]


@pytest.mark.parametrize("validate", ["true", "false"])
def test_interview_question_count_cannot_go_below_company_questions(admin, posting_id, validate):
    for seq in (1, 2, 3):
        _sql("insert into company_question (posting_id, seq, content) values (:p, :s, '질문')", p=posting_id, s=seq)
    settings = {"question_count": 2, "follow_up_enabled": True, "think_time_sec": 30, "answer_time_sec": 90}
    r = _put_interview(admin, posting_id, settings=settings, validate=validate)
    assert r.status_code == 422 and r.json()["code"] == "QUESTION_COUNT_TOO_LOW"
    assert "3개" in r.json()["message"]
    # 같은 개수는 된다
    assert _put_interview(admin, posting_id, settings={**settings, "question_count": 3}).status_code == 200


def test_interview_empty_question_count_is_allowed_with_company_questions_for_draft(admin, posting_id):
    _sql("insert into company_question (posting_id, seq, content) values (:p, 1, '질문')", p=posting_id)
    r = _put_interview(admin, posting_id, settings={"think_time_sec": 10}, validate="false")
    assert r.status_code == 200


def test_interview_other_admin_gets_404(admin, posting_id):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as other:
        _login(other)
        assert other.get(f"/api/admin/postings/{posting_id}/interview-criteria").status_code == 404
        assert _put_interview(other, posting_id).status_code == 404


def test_interview_not_editable(admin, posting_id):
    _sql(
        "update job_posting set write_status = '등록 완료', progress_status = '서류 접수 중' where posting_id = :p",
        p=posting_id,
    )
    r = _put_interview(admin, posting_id)
    assert r.status_code == 409 and r.json()["code"] == "POSTING_NOT_EDITABLE"

# ---------- 기업 질문 (화면 08, ADM-009) ----------
def _company(admin, pid):
    return admin.get(f"/api/admin/postings/{pid}/company-questions").json()


def _put_company(admin, pid, questions=("질문1",), ratio=60, validate="true"):
    body = {"questions": list(questions), "job_question_ratio": ratio}
    return admin.put(f"/api/admin/postings/{pid}/company-questions?validate={validate}", json=body)


def _set_question_count(pid, count):
    _sql("update job_posting set question_count = :c where posting_id = :p", c=count, p=pid)


def test_company_questions_require_login(client):
    assert client.get("/api/admin/postings/1/company-questions").status_code == 401


def test_company_questions_initial_is_blank(admin, posting_id):
    assert _company(admin, posting_id) == {"questions": [], "job_question_ratio": None, "question_count": None}


def test_company_questions_round_trip_keeps_order(admin, posting_id):
    _set_question_count(posting_id, 6)
    assert _put_company(admin, posting_id, ["셋째 아님", "A", "B"], ratio=60).status_code == 200
    data = _company(admin, posting_id)
    assert data == {"questions": ["셋째 아님", "A", "B"], "job_question_ratio": 60, "question_count": 6}
    rows = _sql("select seq, content from company_question where posting_id = :p order by seq", p=posting_id)
    assert [tuple(r) for r in rows] == [(1, "셋째 아님"), (2, "A"), (3, "B")]


def test_company_questions_save_replaces_previous(admin, posting_id):
    _set_question_count(posting_id, 6)
    _put_company(admin, posting_id, ["A", "B", "C"])
    _put_company(admin, posting_id, ["C", "A"], ratio=40)
    assert _company(admin, posting_id)["questions"] == ["C", "A"]


def test_company_questions_zero_is_allowed(admin, posting_id):
    _set_question_count(posting_id, 6)
    assert _put_company(admin, posting_id, [], ratio=50).status_code == 200
    assert _company(admin, posting_id)["questions"] == []


def test_company_questions_blank_rows_are_dropped_and_trimmed(admin, posting_id):
    _set_question_count(posting_id, 6)
    _put_company(admin, posting_id, ["  A  ", "", "   ", "B"], validate="false")
    assert _company(admin, posting_id)["questions"] == ["A", "B"]


@pytest.mark.parametrize("validate", ["true", "false"])
def test_company_questions_cannot_exceed_question_count(admin, posting_id, validate):
    _set_question_count(posting_id, 2)
    r = _put_company(admin, posting_id, ["A", "B", "C"], validate=validate)
    assert r.status_code == 422 and "출제 문제 개수(2개)" in r.json()["message"]
    # 같은 개수는 된다
    assert _put_company(admin, posting_id, ["A", "B"], validate=validate).status_code == 200


@pytest.mark.parametrize("validate", ["true", "false"])
def test_company_questions_need_question_count_first(admin, posting_id, validate):
    r = _put_company(admin, posting_id, ["A"], validate=validate)
    assert r.status_code == 422 and "출제 문제 개수를 먼저" in r.json()["message"]


def test_company_questions_next_needs_question_count_even_if_empty(admin, posting_id):
    r = _put_company(admin, posting_id, [], ratio=50)
    assert r.status_code == 422 and "출제 문제 개수를 먼저" in r.json()["message"]
    # 임시 저장은 된다
    assert _put_company(admin, posting_id, [], ratio=None, validate="false").status_code == 200


def test_company_questions_next_requires_ratio_when_ai_questions_exist(admin, posting_id):
    _set_question_count(posting_id, 3)
    r = _put_company(admin, posting_id, ["A"], ratio=None)
    assert r.status_code == 422 and "비율을 설정" in r.json()["message"]
    assert _put_company(admin, posting_id, ["A"], ratio=None, validate="false").status_code == 200


def test_company_questions_ratio_not_needed_without_ai_questions(admin, posting_id):
    _set_question_count(posting_id, 2)
    assert _put_company(admin, posting_id, ["A", "B"], ratio=None).status_code == 200


@pytest.mark.parametrize("ratio", [0, 100])
def test_company_questions_ratio_bounds_are_allowed(admin, posting_id, ratio):
    _set_question_count(posting_id, 3)
    assert _put_company(admin, posting_id, ["A"], ratio=ratio).status_code == 200
    assert _company(admin, posting_id)["job_question_ratio"] == ratio


@pytest.mark.parametrize("ratio", [-1, 101])
def test_company_questions_ratio_out_of_range(admin, posting_id, ratio):
    _set_question_count(posting_id, 3)
    assert _put_company(admin, posting_id, ["A"], ratio=ratio, validate="false").status_code == 422


def test_company_questions_other_admin_gets_404(admin, posting_id):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as other:
        _login(other)
        assert other.get(f"/api/admin/postings/{posting_id}/company-questions").status_code == 404
        assert _put_company(other, posting_id).status_code == 404


def test_company_questions_not_editable(admin, posting_id):
    _set_question_count(posting_id, 3)
    _sql(
        "update job_posting set write_status = '등록 완료', progress_status = '서류 접수 중' where posting_id = :p",
        p=posting_id,
    )
    r = _put_company(admin, posting_id)
    assert r.status_code == 409 and r.json()["code"] == "POSTING_NOT_EDITABLE"

# ---------- 최종 검토와 등록 (화면 09, ADM-010) ----------
ALL_STEPS = ["info", "doc-items", "doc-criteria", "interview-criteria", "company-questions"]


def _fill_all(admin, pid):
    """모든 단계를 올바르게 채운다 (프로젝트 문서는 선택 사항이라 올리지 않는다)"""
    assert admin.put(f"/api/admin/postings/{pid}/info", json=FULL).status_code == 200
    assert admin.put(f"/api/admin/postings/{pid}/doc-items", json=DOC_ITEMS).status_code == 200
    assert _put_ratios(admin, pid, [30, 30, 20, 20]).status_code == 200
    assert _put_interview(admin, pid).status_code == 200
    assert _put_company(admin, pid, ["Q1", "Q2"], ratio=60).status_code == 200


def _review(admin, pid):
    r = admin.get(f"/api/admin/postings/{pid}/review")
    assert r.status_code == 200
    return r.json()


def test_review_requires_login(client):
    assert client.get("/api/admin/postings/1/review").status_code == 401
    assert client.post("/api/admin/postings/1/publish").status_code == 401


def test_review_of_empty_posting_lists_every_step(admin, posting_id):
    data = _review(admin, posting_id)
    assert data["incomplete_steps"] == ALL_STEPS
    assert data["posting"]["write_status"] == "임시 저장"
    assert [c["criteria_name"] for c in data["doc_criteria"]["criteria"]] == ["이력서", "기술 적용 사례", "포트폴리오", "자기소개"]
    assert [c["criteria_name"] for c in data["interview_criteria"]["criteria"]] == ["내용", "언어", "비언어"]


def test_review_of_complete_posting(admin, posting_id):
    _fill_all(admin, posting_id)
    data = _review(admin, posting_id)
    assert data["incomplete_steps"] == []
    assert data["posting"]["position_name"] == FULL["position_name"]
    assert [s["skill_name"] for s in data["doc_items"]["skills"]] == ["Java", "SQL"]
    assert [c["ratio"] for c in data["doc_criteria"]["criteria"]] == [30, 30, 20, 20]
    assert data["interview_criteria"]["question_count"] == 6
    assert data["company_questions"] == {"questions": ["Q1", "Q2"], "job_question_ratio": 60, "question_count": 6}


def test_review_includes_documents(admin, posting_id):
    admin.post(f"/api/admin/postings/{posting_id}/documents", files={"file": ("소개.pdf", PDF, "application/pdf")})
    docs = _review(admin, posting_id)["posting"]["documents"]
    assert [d["file_name"] for d in docs] == ["소개.pdf"]


@pytest.mark.parametrize(
    "breaker, step",
    [
        ("update job_posting set position_name = null where posting_id = :p", "info"),
        ("delete from essay_topic where posting_id = :p", "doc-items"),
        ("delete from required_skill where posting_id = :p", "doc-items"),
        ("update posting_eval_ratio set ratio = 10 where posting_id = :p and criteria_id = 1", "doc-criteria"),
        ("delete from posting_eval_ratio where posting_id = :p and criteria_id = 2", "doc-criteria"),
        ("update posting_eval_ratio set ratio = 0 where posting_id = :p and criteria_id = 7", "interview-criteria"),
        ("update job_posting set think_time_sec = null where posting_id = :p", "interview-criteria"),
        ("update job_posting set job_question_ratio = null where posting_id = :p", "company-questions"),
    ],
)
def test_review_detects_the_broken_step(admin, posting_id, breaker, step):
    _fill_all(admin, posting_id)
    _sql(breaker, p=posting_id)
    assert step in _review(admin, posting_id)["incomplete_steps"]


def test_review_company_questions_over_count_is_incomplete(admin, posting_id):
    _fill_all(admin, posting_id)
    _sql("update job_posting set question_count = 1 where posting_id = :p", p=posting_id)
    assert _review(admin, posting_id)["incomplete_steps"] == ["company-questions"]


def test_review_without_ai_questions_needs_no_ratio(admin, posting_id):
    _fill_all(admin, posting_id)
    _put_company(admin, posting_id, ["A", "B", "C", "D", "E", "F"], ratio=None)
    assert _review(admin, posting_id)["incomplete_steps"] == []


def test_review_other_admin_gets_404(admin, posting_id):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as other:
        _login(other)
        assert other.get(f"/api/admin/postings/{posting_id}/review").status_code == 404
        assert other.post(f"/api/admin/postings/{posting_id}/publish").status_code == 404


def test_publish_rejects_incomplete_posting(admin, posting_id):
    r = admin.post(f"/api/admin/postings/{posting_id}/publish")
    assert r.status_code == 422 and r.json()["code"] == "POSTING_INVALID"
    for label in ("공고 정보", "서류 문항", "서류 평가기준", "면접 평가기준", "면접 질문"):
        assert label in r.json()["message"]
    assert _review(admin, posting_id)["posting"]["write_status"] == "임시 저장"


def test_publish_names_only_the_incomplete_steps(admin, posting_id):
    _fill_all(admin, posting_id)
    _sql("update posting_eval_ratio set ratio = 10 where posting_id = :p and criteria_id = 1", p=posting_id)
    r = admin.post(f"/api/admin/postings/{posting_id}/publish")
    assert r.status_code == 422 and "서류 평가기준" in r.json()["message"] and "공고 정보" not in r.json()["message"]


def test_publish_completes_posting_without_documents(admin, posting_id):
    _fill_all(admin, posting_id)
    r = admin.post(f"/api/admin/postings/{posting_id}/publish")
    assert r.status_code == 200 and r.json() == {"posting_id": posting_id, "write_status": "등록 완료"}
    detail = admin.get(f"/api/admin/postings/{posting_id}").json()
    assert detail["write_status"] == "등록 완료" and detail["progress_status"] == "모집 전"


def test_publish_twice_is_harmless_and_posting_stays_editable_before_recruiting(admin, posting_id):
    _fill_all(admin, posting_id)
    assert admin.post(f"/api/admin/postings/{posting_id}/publish").status_code == 200
    assert admin.post(f"/api/admin/postings/{posting_id}/publish").status_code == 200
    # 모집 전에는 등록한 뒤에도 수정할 수 있다
    assert admin.put(f"/api/admin/postings/{posting_id}/info", json={**FULL, "position_name": "수정됨"}).status_code == 200


def test_publish_not_editable_after_recruiting_started(admin, posting_id):
    _fill_all(admin, posting_id)
    _sql(
        "update job_posting set write_status = '등록 완료', progress_status = '서류 접수 중' where posting_id = :p",
        p=posting_id,
    )
    r = admin.post(f"/api/admin/postings/{posting_id}/publish")
    assert r.status_code == 409 and r.json()["code"] == "POSTING_NOT_EDITABLE"


def _upload_pdf(admin, pid, name="소개.pdf"):
    r = admin.post(f"/api/admin/postings/{pid}/documents", files={"file": (name, PDF, "application/pdf")})
    assert r.status_code == 201
    return r.json()["document_id"]


def test_document_file_is_served_inline(admin, posting_id):
    doc_id = _upload_pdf(admin, posting_id)
    r = admin.get(f"/api/admin/postings/{posting_id}/documents/{doc_id}/file")
    assert r.status_code == 200 and r.content == PDF
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline")
    assert r.headers["x-content-type-options"] == "nosniff"


def test_document_file_requires_login(client):
    assert client.get("/api/admin/postings/1/documents/1/file").status_code == 401


def test_document_file_of_other_admin_or_unknown_is_404(admin, posting_id):
    from fastapi.testclient import TestClient
    from app.main import app

    doc_id = _upload_pdf(admin, posting_id)
    assert admin.get(f"/api/admin/postings/{posting_id}/documents/{doc_id + 9999}/file").status_code == 404
    with TestClient(app) as other:
        _login(other)
        assert other.get(f"/api/admin/postings/{posting_id}/documents/{doc_id}/file").status_code == 404


def test_document_file_missing_on_disk_is_404(admin, posting_id):
    doc_id = _upload_pdf(admin, posting_id)
    path = _sql("select file_path from posting_document where document_id = :d", d=doc_id)[0][0]
    (Path(get_settings().STORAGE_ROOT) / path).unlink()
    r = admin.get(f"/api/admin/postings/{posting_id}/documents/{doc_id}/file")
    assert r.status_code == 404 and r.json()["code"] == "DOCUMENT_NOT_FOUND"

# ---------- 공고 목록, 이어서 작성, 삭제 (화면 10, ADM-012, ADM-011, ADM-020) ----------
def _list(admin):
    r = admin.get("/api/admin/postings")
    assert r.status_code == 200
    return r.json()


def _draft(admin):
    r = admin.get("/api/admin/postings/draft")
    assert r.status_code == 200
    return r.json()


def _register(admin):
    pid = admin.post("/api/admin/postings").json()["posting_id"]
    _fill_all(admin, pid)
    assert admin.post(f"/api/admin/postings/{pid}/publish").status_code == 200
    return pid


def _applicant_id():
    from fastapi.testclient import TestClient
    from app.main import app

    email = f"{uuid.uuid4().hex}@example.com"
    with TestClient(app) as c:
        c.post(
            "/api/auth/signup",
            json={"role": "지원자", "name": "지원자", "email": email, "password": PASSWORD, "password_confirm": PASSWORD},
        )
    return _sql("select member_id from member where email = :e", e=email)[0][0]


def test_list_requires_login(client):
    assert client.get("/api/admin/postings").status_code == 401
    assert client.get("/api/admin/postings/draft").status_code == 401
    assert client.delete("/api/admin/postings/1").status_code == 401


def test_list_is_empty_for_new_admin(admin):
    assert _list(admin) == []


def test_list_shows_only_registered_postings_newest_first(admin):
    draft_id = admin.post("/api/admin/postings").json()["posting_id"]
    first = _register(admin)
    second = _register(admin)
    items = _list(admin)
    assert [i["posting_id"] for i in items] == [second, first]
    assert draft_id not in [i["posting_id"] for i in items]


def test_list_item_fields(admin):
    pid = _register(admin)
    item = _list(admin)[0]
    assert item["posting_id"] == pid
    assert item["position_name"] == FULL["position_name"] and item["employment_type"] == "정규직"
    assert item["progress_status"] == "모집 전" and item["applicant_count"] == 0
    assert item["doc_start_at"].startswith("2026-10-26T15:00:00")  # 2026-10-27 00:00 +09:00


def test_list_hides_other_admins_postings(admin):
    from fastapi.testclient import TestClient
    from app.main import app

    _register(admin)
    with TestClient(app) as other:
        _login(other)
        assert _list(other) == []


def test_list_counts_only_submitted_applications(admin):
    pid = _register(admin)
    for status in ("제출", "제출", "임시 저장"):
        _sql(
            "insert into application (posting_id, applicant_id, write_status) values (:p, :a, :s)",
            p=pid, a=_applicant_id(), s=status,
        )
    assert _list(admin)[0]["applicant_count"] == 2


def test_draft_is_null_without_draft(admin):
    assert _draft(admin) is None
    _register(admin)
    assert _draft(admin) is None  # 등록한 공고는 이어서 작성 대상이 아니다


def test_draft_returns_latest_draft_of_own(admin):
    admin.post("/api/admin/postings")
    latest = admin.post("/api/admin/postings").json()["posting_id"]
    assert _draft(admin)["posting_id"] == latest


def test_draft_is_not_shared_between_admins(admin, posting_id):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as other:
        _login(other)
        assert _draft(other) is None


def test_draft_resume_step_is_first_incomplete_step(admin, posting_id):
    assert _draft(admin)["resume_step"] == "info"
    admin.put(f"/api/admin/postings/{posting_id}/info", json=FULL)
    assert _draft(admin)["resume_step"] == "doc-items"
    admin.put(f"/api/admin/postings/{posting_id}/doc-items", json=DOC_ITEMS)
    assert _draft(admin)["resume_step"] == "doc-criteria"
    _put_ratios(admin, posting_id, [30, 30, 20, 20])
    assert _draft(admin)["resume_step"] == "interview-criteria"
    _put_interview(admin, posting_id)
    assert _draft(admin)["resume_step"] == "company-questions"
    _put_company(admin, posting_id, ["Q1"], ratio=60)
    draft = _draft(admin)
    assert draft["resume_step"] == "review" and draft["position_name"] == FULL["position_name"]


def test_delete_draft_removes_everything(admin, posting_id):
    _fill_all(admin, posting_id)
    doc_id = _upload_pdf(admin, posting_id)
    path = _sql("select file_path from posting_document where document_id = :d", d=doc_id)[0][0]
    assert (Path(get_settings().STORAGE_ROOT) / path).exists()

    assert admin.delete(f"/api/admin/postings/{posting_id}").status_code == 204
    assert admin.get(f"/api/admin/postings/{posting_id}").status_code == 404
    for table in ("posting_document", "posting_basic_item", "posting_eval_ratio", "required_skill", "essay_topic", "company_question"):
        assert _sql(f"select count(*) from {table} where posting_id = :p", p=posting_id)[0][0] == 0
    assert not (Path(get_settings().STORAGE_ROOT) / path).exists()
    assert _draft(admin) is None


def test_delete_registered_posting_before_recruiting(admin):
    pid = _register(admin)
    assert admin.delete(f"/api/admin/postings/{pid}").status_code == 204
    assert _list(admin) == []


def test_delete_not_allowed_after_recruiting_started(admin, posting_id):
    _fill_all(admin, posting_id)
    _sql("update job_posting set write_status = '등록 완료', progress_status = '서류 접수 중' where posting_id = :p", p=posting_id)
    r = admin.delete(f"/api/admin/postings/{posting_id}")
    assert r.status_code == 409 and r.json()["code"] == "POSTING_NOT_EDITABLE" and "삭제" in r.json()["message"]
    assert admin.get(f"/api/admin/postings/{posting_id}").status_code == 200


def test_delete_other_admins_posting_gets_404(admin, posting_id):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as other:
        _login(other)
        assert other.delete(f"/api/admin/postings/{posting_id}").status_code == 404
    assert admin.get(f"/api/admin/postings/{posting_id}").status_code == 200

# ---------- 공고 상세: 전형별 지원자 수, 등록된 공고 수정 (화면 11, ADM-013, ADM-014~019) ----------
def _stats(admin, pid):
    r = admin.get(f"/api/admin/postings/{pid}/stats")
    assert r.status_code == 200
    return r.json()


def _add_application(pid, status="제출"):
    applicant = _applicant_id()
    _sql(
        "insert into application (posting_id, applicant_id, write_status) values (:p, :a, :s)",
        p=pid, a=applicant, s=status,
    )
    return _sql(
        "select application_id from application where posting_id = :p and applicant_id = :a", p=pid, a=applicant
    )[0][0]


def test_stats_requires_login(client):
    assert client.get("/api/admin/postings/1/stats").status_code == 401


def test_stats_other_admin_gets_404(admin, posting_id):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as other:
        _login(other)
        assert other.get(f"/api/admin/postings/{posting_id}/stats").status_code == 404


def test_stats_are_zero_without_applications(admin, posting_id):
    assert _stats(admin, posting_id) == {
        "submitted_count": 0,
        "interview_target_count": 0,
        "interview_done_count": 0,
        "skill_shortfall_count": 0,
        "ai_unhandled_error_count": 0,
    }


def test_stats_count_submitted_target_and_done(admin, posting_id):
    first = _add_application(posting_id)
    second = _add_application(posting_id)
    _add_application(posting_id, "임시 저장")  # 제출하지 않은 지원서는 세지 않는다
    # 서류 전형: 첫째만 합격
    _sql("insert into application_stage (application_id, stage_type, result) values (:a, '서류', '합격')", a=first)
    _sql("insert into application_stage (application_id, stage_type, result) values (:a, '서류', '불합격')", a=second)
    _sql("insert into application_stage (application_id, stage_type, result) values (:a, '면접', '합격')", a=first)  # 면접 결과는 대상이 아니다
    # 면접: 첫째는 두 번 완료(한 명으로 센다), 둘째는 중단
    _sql("insert into interview_session (application_id, status, attempt_no) values (:a, '완료', 1)", a=first)
    _sql("insert into interview_session (application_id, status, attempt_no) values (:a, '완료', 2)", a=first)
    _sql("insert into interview_session (application_id, status, attempt_no) values (:a, '중단', 1)", a=second)
    stats = _stats(admin, posting_id)
    assert (stats["submitted_count"], stats["interview_target_count"], stats["interview_done_count"]) == (2, 1, 1)


def test_stats_are_per_posting(admin, posting_id):
    other_posting = admin.post("/api/admin/postings").json()["posting_id"]
    _add_application(other_posting)
    assert _stats(admin, posting_id)["submitted_count"] == 0
    assert _stats(admin, other_posting)["submitted_count"] == 1


def test_registered_posting_is_validated_even_for_draft_save(admin, posting_id):
    _fill_all(admin, posting_id)
    assert admin.post(f"/api/admin/postings/{posting_id}/publish").status_code == 200
    base = f"/api/admin/postings/{posting_id}"
    assert admin.put(f"{base}/info?validate=false", json={**FULL, "position_name": None}).status_code == 422
    assert admin.put(f"{base}/doc-items?validate=false", json={}).status_code == 422
    assert _put_ratios(admin, posting_id, [30, None, None, None], validate="false").status_code == 422
    assert _put_interview(admin, posting_id, ratios=(50, None, None), settings={"think_time_sec": 5}, validate="false").status_code == 422
    assert _put_company(admin, posting_id, ["Q1"], ratio=None, validate="false").status_code == 422
    # 거절된 요청은 저장된 값을 바꾸지 않는다
    assert _review(admin, posting_id)["incomplete_steps"] == []
    assert _review(admin, posting_id)["posting"]["position_name"] == FULL["position_name"]


def test_registered_posting_can_be_updated_with_valid_values(admin, posting_id):
    _fill_all(admin, posting_id)
    admin.post(f"/api/admin/postings/{posting_id}/publish")
    r = admin.put(f"/api/admin/postings/{posting_id}/info?validate=false", json={**FULL, "position_name": "수정된 공고명"})
    assert r.status_code == 200 and r.json()["position_name"] == "수정된 공고명"
    assert _review(admin, posting_id)["posting"]["write_status"] == "등록 완료"


def test_draft_posting_still_allows_draft_save(admin, posting_id):
    assert admin.put(f"/api/admin/postings/{posting_id}/info?validate=false", json={}).status_code == 200

# ---------- 대시보드: 필수 기술 미달 탈락, AI 미처리 오류 (화면 03, ADM-003) ----------
def _add_session(application_id, status="완료"):
    _sql("insert into interview_session (application_id, status, attempt_no) values (:a, :s, 1)", a=application_id, s=status)
    return _sql("select max(session_id) from interview_session where application_id = :a", a=application_id)[0][0]


def test_stats_count_skill_shortfall(admin, posting_id):
    first, second, third = (_add_application(posting_id) for _ in range(3))
    for application, result in ((first, "필수 기술 미달"), (second, "필수 기술 미달"), (third, "합격")):
        _sql("insert into application_stage (application_id, stage_type, result) values (:a, '서류', :r)", a=application, r=result)
    # 면접 전형의 결과는 세지 않는다
    _sql("insert into application_stage (application_id, stage_type, result) values (:a, '면접', '불합격')", a=first)
    stats = _stats(admin, posting_id)
    assert stats["skill_shortfall_count"] == 2 and stats["interview_target_count"] == 1


def test_stats_count_only_unhandled_inquiries(admin, posting_id):
    session = _add_session(_add_application(posting_id))
    for code in ("UNRESOLVED_SYSTEM", "UNRESOLVED_APPLICANT", "RESOLVED_SYSTEM", "RESOLVED_APPLICANT"):
        _sql("insert into inquiry (session_id, judgment_code) values (:s, :c)", s=session, c=code)
    # 판단 결과가 아직 없는 문의는 미처리로 세지 않는다
    _sql("insert into inquiry (session_id) values (:s)", s=session)
    assert _stats(admin, posting_id)["ai_unhandled_error_count"] == 2


def test_stats_unhandled_errors_are_per_posting(admin, posting_id):
    other = admin.post("/api/admin/postings").json()["posting_id"]
    _sql("insert into inquiry (session_id, judgment_code) values (:s, 'UNRESOLVED_UNKNOWN')", s=_add_session(_add_application(other)))
    assert _stats(admin, posting_id)["ai_unhandled_error_count"] == 0
    assert _stats(admin, other)["ai_unhandled_error_count"] == 1


# ---------- 지원자 채용공고 목록 (APP-003) ----------
def _public(client):
    r = client.get("/api/postings")
    assert r.status_code == 200
    return r.json()


def test_public_list_needs_no_login(client):
    assert isinstance(_public(client), list)


def test_public_list_shows_registered_including_before_recruit_and_hides_drafts(admin, client):
    draft_id = admin.post("/api/admin/postings").json()["posting_id"]
    pid = _register(admin)  # 등록 직후 진행 상태는 '모집 전'
    items = {i["posting_id"]: i for i in _public(client)}
    assert pid in items and draft_id not in items
    assert items[pid]["progress_status"] == "모집 전"
    assert items[pid]["position_name"] == FULL["position_name"]


def test_public_list_is_newest_first_and_hides_applicant_count(admin, client):
    first, second = _register(admin), _register(admin)
    items = _public(client)
    ids = [i["posting_id"] for i in items]
    assert ids.index(second) < ids.index(first)
    assert all("applicant_count" not in i for i in items)


def test_public_list_is_open_to_admin_and_applicant(admin, client):
    pid = _register(admin)
    applicant = _login(TestClient(client.app), "지원자")
    assert pid in [i["posting_id"] for i in _public(applicant)]
    assert pid in [i["posting_id"] for i in _public(admin)]


# ---------- 지원자 채용공고 상세 (APP-004) ----------
def test_public_detail_needs_no_login_and_shows_basic_info_and_schedule(admin, client):
    pid = _register(admin)
    r = client.get(f"/api/postings/{pid}")
    assert r.status_code == 200
    d = r.json()
    assert d["position_name"] == FULL["position_name"] and d["job_category"] == FULL["job_category"]
    assert d["employment_type"] == "정규직" and d["job_description"] == FULL["job_description"]
    assert d["progress_status"] == "모집 전"
    assert d["doc_end_at"].startswith("2026-11-05T14:59") and d["interview_result_at"].startswith("2026-11-20T01:00")


def test_public_detail_hides_internal_info(admin, client):
    d = client.get(f"/api/postings/{_register(admin)}").json()
    for key in ("functional_talent", "nonfunctional_talent", "documents", "write_status"):
        assert key not in d


def test_public_detail_of_draft_or_missing_is_404(admin, client):
    draft_id = admin.post("/api/admin/postings").json()["posting_id"]
    assert client.get(f"/api/postings/{draft_id}").status_code == 404
    assert client.get("/api/postings/999999999").status_code == 404
