# File Path: backend/app/schemas/usage_purpose.py
# Timestamp: 2026-05-26T12:00:00+08:00
# Version: v0.1

from datetime import datetime

from pydantic import BaseModel, Field


class UsagePurposeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    status: str = Field(default="ACTIVE", min_length=1, max_length=32)


class UsagePurposeRead(BaseModel):
    id: int
    code: str
    name: str
    description: str | None
    status: str
    created_by_user_id: int | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
