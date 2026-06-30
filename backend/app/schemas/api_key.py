# File Path: backend/app/schemas/api_key.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from datetime import datetime

from pydantic import BaseModel, Field


class APIKeyCreate(BaseModel):
    provider_id: int
    name: str = Field(min_length=1, max_length=120)
    plain_secret: str = Field(min_length=8, max_length=512)
    owner_user_id: int
    department_id: int
    expires_at: datetime | None = None
    rotation_due_at: datetime | None = None
    is_primary: bool = False


class APIKeyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    owner_user_id: int | None = None
    department_id: int | None = None
    status: str | None = None
    expires_at: datetime | None = None
    rotation_due_at: datetime | None = None


class APIKeyRotateRequest(BaseModel):
    new_plain_secret: str = Field(min_length=8, max_length=512)
    reason: str = Field(min_length=4, max_length=255)


class APIKeyDisableRequest(BaseModel):
    reason: str = Field(min_length=4, max_length=255)


class APIKeyRead(BaseModel):
    id: int
    provider_id: int
    name: str
    masked_key: str
    owner_user_id: int
    department_id: int
    status: str
    expires_at: datetime | None
    last_rotated_at: datetime | None
    rotation_due_at: datetime | None
    is_primary: bool

    class Config:
        from_attributes = True
