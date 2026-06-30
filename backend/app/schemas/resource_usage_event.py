# File Path: backend/app/schemas/resource_usage_event.py
# Timestamp: 2026-05-26T12:00:00+08:00
# Version: v0.1

from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class ResourceUsageEventCreate(BaseModel):
    api_key_id: int | None = None
    ai_account_id: int | None = None
    department_id: int | None = None
    project_id: int | None = None
    actor_user_id: int | None = None
    request_id: str | None = Field(default=None, max_length=80)
    event_source: str = Field(default="MANUAL", min_length=1, max_length=64)
    external_event_id: str | None = Field(default=None, max_length=128)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: Decimal = Field(default=Decimal("0"))
    currency: str = Field(default="USD", min_length=3, max_length=16)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata_json: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_payload(self):
        if (self.api_key_id is None) == (self.ai_account_id is None):
            raise ValueError("api_key_id 與 ai_account_id 必須擇一")

        if self.estimated_cost_usd < 0:
            raise ValueError("estimated_cost_usd 不可為負")

        calculated_total = self.input_tokens + self.output_tokens
        if self.total_tokens is None:
            self.total_tokens = calculated_total
        elif self.total_tokens < calculated_total:
            raise ValueError("total_tokens 不可小於 input_tokens + output_tokens")

        return self


class ResourceUsageEventRead(BaseModel):
    id: int
    api_key_id: int | None
    ai_account_id: int | None
    department_id: int | None
    project_id: int | None
    actor_user_id: int | None
    request_id: str | None
    event_source: str
    external_event_id: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: Decimal
    currency: str
    occurred_at: datetime
    metadata_json: dict
    created_at: datetime

    class Config:
        from_attributes = True
