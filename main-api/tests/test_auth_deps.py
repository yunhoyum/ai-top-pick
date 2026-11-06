import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.deps import require_admin, require_applicant
from app.core.errors import register_handlers

PASSWORD = "password1"


def _signup_login(client, role):
    email = f"{uuid.uuid4().hex}@example.com"
    body = {
        "role": role,
        "name": "홍길동",
        "email": email,
        "password": PASSWORD,
        "password_confirm": PASSWORD,
        "company_name": "테스트회사" if role == "관리자" else None,
    }
    member_id = client.post("/api/auth/signup", json=body).json()["member_id"]
    r = client.post("/api/auth/login", json={"role": role, "email": email, "password": PASSWORD})
    assert r.status_code == 200
    return member_id, client.cookies["access_token"]


def _token(member_id, exp_delta=timedelta(minutes=5), secret=None):
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": str(member_id), "role": "관리자", "iat": now, "exp": now + exp_delta}
    return jwt.encode(payload, secret or s.JWT_SECRET, algorithm=s.JWT_ALGORITHM)


def _me(client, token=None):
    client.cookies.clear()
    if token:
        client.cookies.set("access_token", token)
    return client.get("/api/auth/me")


def test_me_returns_current_member(client):
    member_id, token = _signup_login(client, "관리자")
    r = _me(client, token)
    assert r.status_code == 200
    assert r.json()["member_id"] == member_id and r.json()["role"] == "관리자"


def test_me_without_token(client):
    r = _me(client)
    assert r.status_code == 401
    assert r.json()["code"] == "UNAUTHENTICATED"


def test_me_expired_token(client):
    member_id, _ = _signup_login(client, "관리자")
    r = _me(client, _token(member_id, exp_delta=timedelta(minutes=-1)))
    assert r.status_code == 401
    assert r.json()["code"] == "TOKEN_EXPIRED"


@pytest.mark.parametrize("kind", ["garbage", "wrong_secret", "unknown_member"])
def test_me_invalid_token(client, kind):
    member_id, _ = _signup_login(client, "관리자")
    bad = {
        "garbage": "not-a-jwt",
        "wrong_secret": _token(member_id, secret="x" * 32),  # 서명이 다른 토큰
        "unknown_member": _token(2**60),  # 서명은 맞지만 없는 회원
    }[kind]
    r = _me(client, bad)
    assert r.status_code == 401
    assert r.json()["code"] == "UNAUTHENTICATED"


def test_logout_clears_cookie(client):
    _signup_login(client, "관리자")
    r = client.post("/api/auth/logout")
    assert r.status_code == 204
    cookie = r.headers["set-cookie"].lower()
    assert "access_token" in cookie and "max-age=0" in cookie
    assert client.get("/api/auth/me").status_code == 401  # 쿠키가 지워져 다시 401


# ---- 역할 검사: 실제 관리자·지원자 전용 API가 생기기 전이라 임시 앱에 붙여서 확인한다 ----
role_app = FastAPI()
register_handlers(role_app)


@role_app.get("/admin-only")
async def admin_only(member=Depends(require_admin)):
    return {"member_id": member.member_id}


@role_app.get("/applicant-only")
async def applicant_only(member=Depends(require_applicant)):
    return {"member_id": member.member_id}


@pytest.mark.parametrize(
    "role,path,status",
    [
        ("관리자", "/admin-only", 200),
        ("관리자", "/applicant-only", 403),
        ("지원자", "/applicant-only", 200),
        ("지원자", "/admin-only", 403),
    ],
)
def test_role_check(client, role, path, status):
    _, token = _signup_login(client, role)
    with TestClient(role_app, cookies={"access_token": token}) as c:
        r = c.get(path)
    assert r.status_code == status
    if status == 403:
        assert r.json()["code"] == "FORBIDDEN"


def test_role_check_without_login(client):
    with TestClient(role_app) as c:
        assert c.get("/admin-only").status_code == 401
