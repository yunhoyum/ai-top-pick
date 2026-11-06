import uuid

import pytest
from sqlalchemy import create_engine, text

from app.core.config import get_settings


def _body(**over):
    body = {
        "role": "지원자",
        "name": "홍길동",
        "email": f"{uuid.uuid4().hex}@example.com",
        "password": "password1",
        "password_confirm": "password1",
    }
    body.update(over)
    return body


@pytest.fixture
def db():
    engine = create_engine(get_settings().sqlalchemy_url)
    with engine.connect() as conn:
        yield conn
    engine.dispose()


def test_applicant_signup(client, db):
    body = _body()
    r = client.post("/api/auth/signup", json=body)
    assert r.status_code == 201
    out = r.json()
    assert out["role"] == "지원자" and out["email"] == body["email"]
    assert "password" not in out
    row = db.execute(
        text("select password, company_id from member where email=:e"), {"e": body["email"]}
    ).one()
    assert row.password != "password1" and row.password.startswith("$2")  # bcrypt 해시
    assert row.company_id is None


def test_admin_signup_links_same_company(client, db):
    name = f"회사-{uuid.uuid4().hex[:8]}"
    for _ in range(2):
        r = client.post("/api/auth/signup", json=_body(role="관리자", company_name=name))
        assert r.status_code == 201
    count = db.execute(
        text("select count(*) from company where company_name=:n"), {"n": name}
    ).scalar()
    assert count == 1  # 같은 이름이면 새로 만들지 않고 연결한다


def test_admin_requires_company_name(client):
    assert client.post("/api/auth/signup", json=_body(role="관리자")).status_code == 422


def test_duplicate_email(client):
    body = _body()
    assert client.post("/api/auth/signup", json=body).status_code == 201
    r = client.post("/api/auth/signup", json=body)
    assert r.status_code == 409
    assert r.json()["code"] == "EMAIL_DUPLICATED"


@pytest.mark.parametrize(
    "over",
    [
        {"password": "short1", "password_confirm": "short1"},  # 8자 미만
        {"password_confirm": "different1"},  # 확인 불일치
        {"email": "not-an-email"},
        {"role": "기타"},
        {"password": "가" * 25, "password_confirm": "가" * 25},  # 75바이트 > bcrypt 72바이트
    ],
)
def test_invalid_input(client, over):
    assert client.post("/api/auth/signup", json=_body(**over)).status_code == 422
