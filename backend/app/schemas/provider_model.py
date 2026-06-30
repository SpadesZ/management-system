# File Path: backend/app/schemas/provider_model.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ModelCreate(BaseModel):
    provider_id: int
    model_code: str = Field(min_length=2, max_length=128)
    display_name: str = Field(min_length=1, max_length=128)
    context_window: int = Field(ge=0)
    capabilities_json: dict = Field(default_factory=dict)
    status: str = "ACTIVE"


class ModelUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    context_window: int | None = Field(default=None, ge=0)
    capabilities_json: dict | None = None
    status: str | None = None


class ModelRead(BaseModel):
    id: int
    provider_id: int
    model_code: str
    display_name: str
    context_window: int
    capabilities_json: dict
    status: str

    class Config:
        from_attributes = True


class ModelPriceCreate(BaseModel):
    model_id: int
    input_price_per_1m: Decimal
    output_price_per_1m: Decimal
    currency: str = Field(default="USD", max_length=16)
    effective_from: datetime
    effective_to: datetime | None = None


class ModelPriceRead(BaseModel):
    id: int
    model_id: int
    input_price_per_1m: Decimal
    output_price_per_1m: Decimal
    currency: str
    effective_from: datetime
    effective_to: datetime | None

    class Config:
        from_attributes = True
