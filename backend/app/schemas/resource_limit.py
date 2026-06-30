# File Path: backend/app/schemas/resource_limit.py
# Timestamp: 2026-05-26T12:00:00+08:00
# Version: v0.1

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class ResourceLimitStateCreate(BaseModel):
    api_key_id: int | None = None
    ai_account_id: int | None = None
    tokens_5h: int = Field(default=0, ge=0)
    tokens_today: int = Field(default=0, ge=0)
    tokens_week: int = Field(default=0, ge=0)
    tokens_month: int = Field(default=0, ge=0)
    limit_5h: int | None = Field(default=None, ge=0)
    limit_day: int | None = Field(default=None, ge=0)
    limit_week: int | None = Field(default=None, ge=0)
    limit_month: int | None = Field(default=None, ge=0)
    status: str = "ACTIVE"

    @model_validator(mode="after")
    def validate_asset(self):
        if (self.api_key_id is None) == (self.ai_account_id is None):
            raise ValueError("api_key_id 與 ai_account_id 必須擇一")
        return self


class ResourceLimitStateUpdate(BaseModel):
    tokens_5h: int | None = Field(default=None, ge=0)
    tokens_today: int | None = Field(default=None, ge=0)
    tokens_week: int | None = Field(default=None, ge=0)
    tokens_month: int | None = Field(default=None, ge=0)
    limit_5h: int | None = Field(default=None, ge=0)
    limit_day: int | None = Field(default=None, ge=0)
    limit_week: int | None = Field(default=None, ge=0)
    limit_month: int | None = Field(default=None, ge=0)
    status: str | None = None


class ResourceLimitStateRead(BaseModel):
    id: int
    api_key_id: int | None
    ai_account_id: int | None
    tokens_5h: int
    tokens_today: int
    tokens_week: int
    tokens_month: int
    limit_5h: int | None
    limit_day: int | None
    limit_week: int | None
    limit_month: int | None
    utilization_pct: Decimal
    window_5h_started_at: datetime | None
    status: str
    updated_by_user_id: int | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
