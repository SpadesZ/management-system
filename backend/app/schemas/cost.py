# File Path: backend/app/schemas/cost.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from decimal import Decimal

from pydantic import BaseModel


class CostSummaryItem(BaseModel):
    key: str
    request_count: int
    total_tokens: int
    total_cost_usd: Decimal


class DashboardSummaryResponse(BaseModel):
    today_tokens: int
    today_cost_usd: Decimal
    month_tokens: int
    month_cost_usd: Decimal


class AlertRead(BaseModel):
    id: int
    severity: str
    title: str
    content: str
    status: str

    class Config:
        from_attributes = True
