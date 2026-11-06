from typing import Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.domain.enums import Role


class SignupRequest(BaseModel):
    role: Role
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8)
    password_confirm: str
    # 관리자만 필수 (화면 02 '회사명 (관리자)')
    company_name: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def check(self) -> Self:
        if self.password != self.password_confirm:
            raise ValueError("비밀번호 확인이 일치하지 않습니다.")
        # bcrypt는 72바이트까지만 받는다
        if len(self.password.encode()) > 72:
            raise ValueError("비밀번호가 너무 깁니다.")
        if self.role == Role.ADMIN and not (self.company_name and self.company_name.strip()):
            raise ValueError("관리자는 회사명이 필요합니다.")
        return self


class LoginRequest(BaseModel):
    role: Role
    email: EmailStr
    password: str = Field(min_length=1)


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    member_id: int
    role: str
    name: str
    email: str
