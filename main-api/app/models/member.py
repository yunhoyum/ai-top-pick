from sqlalchemy import BigInteger, ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, in_check
from app.domain.enums import Role


class Company(Base):
    __tablename__ = "company"

    company_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255))


class Member(Base):
    __tablename__ = "member"
    __table_args__ = (in_check("role", Role),)

    member_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # 관리자만 값이 있고 지원자는 NULL
    company_id: Mapped[int | None] = mapped_column(ForeignKey("company.company_id"))
    role: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password: Mapped[str] = mapped_column(String(255))
