# File Path: backend/app/schemas/department.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from decimal import Decimal

from pydantic import BaseModel, Field


class DepartmentCreate(BaseModel):
    parent_id: int | None = None
    name: str = Field(min_length=1, max_length=120)
    cost_center_code: str | None = Field(default=None, max_length=64)
    manager_user_id: int | None = None
    monthly_budget_usd: Decimal = Decimal("0")
    status: str = "ACTIVE"


class DepartmentUpdate(BaseModel):
    parent_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    cost_center_code: str | None = Field(default=None, max_length=64)
    manager_user_id: int | None = None
    monthly_budget_usd: Decimal | None = None
    status: str | None = None


class DepartmentRead(BaseModel):
    id: int
    parent_id: int | None
    name: str
    cost_center_code: str | None
    manager_user_id: int | None
    monthly_budget_usd: Decimal
    status: str

    class Config:
        from_attributes = True
