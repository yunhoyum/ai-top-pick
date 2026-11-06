import bcrypt


def hash_password(raw: str) -> str:
    """비밀번호를 bcrypt로 해시한다."""
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
