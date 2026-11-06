"""Alembic이 모든 테이블을 알 수 있도록 모델 모듈을 모두 불러온다."""

from app.models import (  # noqa: F401
    application,
    batch,
    inquiry,
    interview,
    member,
    posting,
    report,
)
