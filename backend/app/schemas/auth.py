# File Path: backend/app/schemas/auth.py
# Timestamp: 2026-05-26T12:00:00+08:00
# Version: v0.2

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    employee_no: str | None = Field(default=None, min_length=3, max_length=64)
    department_id: int | None = None


class RegisterDepartmentOption(BaseModel):
    id: int
    name: str


class RegisterOptionsResponse(BaseModel):
    departments: list[RegisterDepartmentOption]


class RegisterResponse(BaseModel):
    id: int
    employee_no: str
    name: str
    email: str
    department_id: int
    role: str
    status: str
    message: str = "註冊成功，請使用新帳號登入"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: int
    employee_no: str
    name: str
    email: str
    department_id: int
    role: str
    status: str

    class Config:
        from_attributes = True
