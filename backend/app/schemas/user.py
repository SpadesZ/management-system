# File Path: backend/app/schemas/user.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    employee_no: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    department_id: int
    manager_id: int | None = None
    role: str
    status: str = "ACTIVE"


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    department_id: int | None = None
    manager_id: int | None = None
    role: str | None = None
    status: str | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserRead(BaseModel):
    id: int
    employee_no: str
    name: str
    email: EmailStr
    department_id: int
    manager_id: int | None
    role: str
    status: str

    class Config:
        from_attributes = True
