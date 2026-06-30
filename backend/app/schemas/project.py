# File Path: backend/app/schemas/project.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    department_id: int
    owner_user_id: int
    status: str = "ACTIVE"


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    department_id: int | None = None
    owner_user_id: int | None = None
    status: str | None = None


class ProjectRead(BaseModel):
    id: int
    code: str
    name: str
    department_id: int
    owner_user_id: int
    status: str

    class Config:
        from_attributes = True
