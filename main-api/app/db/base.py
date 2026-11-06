from enum import Enum

from sqlalchemy import CheckConstraint, MetaData
from sqlalchemy.orm import DeclarativeBase

# 제약 이름을 규칙으로 정한다. Alembic이 이름 없는 제약을 다루지 못하는 문제를 막는다
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """모든 ORM 모델의 부모 클래스."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def in_check(column: str, enum: type[Enum]) -> CheckConstraint:
    """명세서의 '값: A/B/C' 제약. NULL은 통과한다."""
    values = ", ".join(f"'{e.value}'" for e in enum)
    return CheckConstraint(f"{column} IN ({values})", name=f"{column}_valid")
