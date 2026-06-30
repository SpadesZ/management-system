# File Path: backend/app/schemas/ai_account.py
# Timestamp: 2026-05-26T21:00:00+08:00
# Version: v0.2

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class AIAccountCreate(BaseModel):
    vendor: str = Field(min_length=1, max_length=64)
    product: str = Field(min_length=1, max_length=64)
    plan: str = Field(min_length=1, max_length=64)
    seats: int = Field(ge=0)
    monthly_cost_usd: Decimal
    renewal_date: datetime | None = None
    owner_user_id: int
    status: str = "ACTIVE"


class AIAccountUpdate(BaseModel):
    plan: str | None = Field(default=None, min_length=1, max_length=64)
    seats: int | None = Field(default=None, ge=0)
    monthly_cost_usd: Decimal | None = None
    renewal_date: datetime | None = None
    owner_user_id: int | None = None
    status: str | None = None


class AIAccountAssignmentRequest(BaseModel):
    user_id: int


class AIAccountRead(BaseModel):
    id: int
    vendor: str
    product: str
    plan: str
    seats: int
    monthly_cost_usd: Decimal
    renewal_date: datetime | None
    owner_user_id: int
    status: str

    class Config:
        from_attributes = True


class AIAccountCredentialCreate(BaseModel):
    credential_name: str = Field(min_length=1, max_length=120)
    credential_type: str = Field(default="PASSWORD", pattern="^(PASSWORD|TOKEN|COOKIE|OTHER)$")
    plain_secret: str = Field(min_length=4, max_length=4096)
    expires_at: datetime | None = None


class AIAccountCredentialRotateRequest(BaseModel):
    new_plain_secret: str = Field(min_length=4, max_length=4096)


class AIAccountCredentialRead(BaseModel):
    id: int
    ai_account_id: int
    credential_name: str
    credential_type: str
    masked_secret: str
    status: str
    expires_at: datetime | None
    last_rotated_at: datetime | None
    created_by_user_id: int | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AIAccountAccessGrantCreate(BaseModel):
    user_id: int
    grant_reason: str | None = Field(default=None, max_length=1000)


class AIAccountAccessGrantRevokeRequest(BaseModel):
    revoke_reason: str | None = Field(default=None, max_length=1000)


class AIAccountAccessGrantRead(BaseModel):
    id: int
    ai_account_id: int
    user_id: int
    granted_by_user_id: int | None
    grant_reason: str | None
    status: str
    granted_at: datetime
    revoked_by_user_id: int | None
    revoke_reason: str | None
    revoked_at: datetime | None

    class Config:
        from_attributes = True


class AIAccountHistoryRead(BaseModel):
    id: int
    ai_account_id: int
    event_type: str
    actor_user_id: int | None
    event_time: datetime
    detail_json: dict

    class Config:
        from_attributes = True
