# File Path: backend/app/schemas/gateway.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from decimal import Decimal

from pydantic import BaseModel, Field


class GatewayChatRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=80)
    idempotency_key: str = Field(min_length=8, max_length=80)
    provider_code: str = Field(min_length=2, max_length=64)
    model_code: str = Field(min_length=2, max_length=128)
    project_id: int | None = None
    message: str = Field(min_length=1, max_length=60000)
    metadata_json: dict = Field(default_factory=dict)


class UsageInfo(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: Decimal


class GatewayChatResponse(BaseModel):
    request_id: str
    provider: str
    model: str
    answer: str
    usage: UsageInfo
    remaining_budget_usd: Decimal
    idempotent_replay: bool = False


class GatewayErrorResponse(BaseModel):
    request_id: str
    error_code: str
    message: str
    retryable: bool
