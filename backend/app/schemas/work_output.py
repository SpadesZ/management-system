# File Path: backend/app/schemas/work_output.py
# Timestamp: 2026-05-26T12:00:00+08:00
# Version: v0.1

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


WorkOutputStatus = Literal["DRAFT", "SUBMITTED", "APPROVED", "REJECTED"]


class WorkOutputCreate(BaseModel):
    usage_purpose_id: int
    department_id: int | None = None
    project_id: int | None = None
    api_key_id: int | None = None
    ai_account_id: int | None = None
    cost_ledger_id: int | None = None
    request_id: str | None = Field(default=None, max_length=80)
    output_title: str = Field(min_length=1, max_length=255)
    output_summary: str | None = Field(default=None, max_length=8000)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cost_usd: Decimal = Field(default=Decimal("0"))
    value_usd: Decimal = Field(default=Decimal("0"))
    currency: str = Field(default="USD", min_length=3, max_length=16)
    metadata_json: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_payload(self):
        if (self.api_key_id is None) == (self.ai_account_id is None):
            raise ValueError("api_key_id 與 ai_account_id 必須擇一")

        if self.cost_usd < 0:
            raise ValueError("cost_usd 不可為負")
        if self.value_usd < 0:
            raise ValueError("value_usd 不可為負")

        calculated_total = self.input_tokens + self.output_tokens
        if self.total_tokens is None:
            self.total_tokens = calculated_total
        elif self.total_tokens < calculated_total:
            raise ValueError("total_tokens 不可小於 input_tokens + output_tokens")

        return self


class WorkOutputDecisionRequest(BaseModel):
    review_comment: str | None = Field(default=None, max_length=2000)


class WorkOutputRead(BaseModel):
    id: int
    usage_purpose_id: int
    user_id: int
    department_id: int
    project_id: int | None
    api_key_id: int | None
    ai_account_id: int | None
    cost_ledger_id: int | None
    request_id: str | None
    output_title: str
    output_summary: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: Decimal
    value_usd: Decimal
    currency: str
    status: WorkOutputStatus
    submitted_at: datetime | None
    reviewer_user_id: int | None
    review_comment: str | None
    resolved_at: datetime | None
    metadata_json: dict
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
