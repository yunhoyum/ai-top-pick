import uuid

import jwt
import pytest

from app.core.config import get_settings

PASSWORD = "password1"


@pytest.fixture
def account(client):
    """가입해 둔 관리자 계정."""
    email = f"{uuid.uuid4().hex}@example.com"
    r = client.post(
        "/api/auth/signup",
        json={
            "role": "관리자",
            "name": "홍길동",
            "email": email,
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "company_name": "테스트회사",
        },
    )
    assert r.status_code == 201
    return {"member_id": r.json()["member_id"], "email": email}


def _login(client, account, **over):
    body = {"role": "관리자", "email": account["email"], "password": PASSWORD}
    body.update(over)
    return client.post("/api/auth/login", json=body)


def test_login_sets_httponly_jwt_cookie(client, account):
    r = _login(client, account)
    assert r.status_code == 200
    assert r.json() == {
        "member_id": account["member_id"],
        "role": "관리자",
        "name": "홍길동",
        "email": account["email"],
    }
    # 토큰은 본문이 아니라 쿠키로만 내려간다
    assert "token" not in r.text
    cookie = r.headers["set-cookie"].lower()
    assert "access_token=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert "path=/" in cookie

    s = get_settings()
    payload = jwt.decode(client.cookies["access_token"], s.JWT_SECRET, algorithms=[s.JWT_ALGORITHM])
    assert payload["sub"] == str(account["member_id"])
    assert payload["role"] == "관리자"
    assert payload["exp"] - payload["iat"] == s.JWT_EXPIRE_MIN * 60


@pytest.mark.parametrize(
    "over",
    [
        {"password": "wrong-password"},  # 비밀번호 틀림
        {"role": "지원자"},  # 가입한 역할과 다름
        {"email": "nobody@example.com"},  # 없는 계정
    ],
)
def test_login_failure_is_uniform_and_sets_no_cookie(client, account, over):
    r = _login(client, account, **over)
    assert r.status_code == 401
    assert r.json() == {
        "code": "LOGIN_FAILED",
        "message": "이메일 또는 비밀번호가 올바르지 않습니다.",
    }
    assert "set-cookie" not in r.headers


def test_login_invalid_input(client, account):
    assert _login(client, account, email="not-an-email").status_code == 422
    assert _login(client, account, password="").status_code == 422
    assert _login(client, account, role="기타").status_code == 422
