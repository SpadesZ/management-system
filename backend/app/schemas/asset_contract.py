# File Path: backend/app/schemas/asset_contract.py
# Timestamp: 2026-05-26T12:00:00+08:00
# Version: v0.1

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


BillingCycle = Literal["MONTHLY", "YEARLY", "USAGE_BASED"]


class AssetContractCreate(BaseModel):
    api_key_id: int | None = None
    ai_account_id: int | None = None
    billing_cycle: BillingCycle
    monthly_fee_usd: Decimal | None = None
    yearly_fee_usd: Decimal | None = None
    currency: str = Field(default="USD", min_length=3, max_length=16)
    start_date: date
    end_date: date | None = None
    auto_renew: bool = False
    payment_method: str | None = Field(default=None, max_length=64)
    status: str = "ACTIVE"
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_contract(self):
        if (self.api_key_id is None) == (self.ai_account_id is None):
            raise ValueError("api_key_id 與 ai_account_id 必須擇一")

        if self.end_date is not None and self.end_date <= self.start_date:
            raise ValueError("end_date 必須晚於 start_date")

        if self.monthly_fee_usd is not None and self.monthly_fee_usd < 0:
            raise ValueError("monthly_fee_usd 不可為負")
        if self.yearly_fee_usd is not None and self.yearly_fee_usd < 0:
            raise ValueError("yearly_fee_usd 不可為負")

        if self.billing_cycle == "MONTHLY":
            if self.monthly_fee_usd is None or self.yearly_fee_usd is not None:
                raise ValueError("MONTHLY 合約需填 monthly_fee_usd，且 yearly_fee_usd 必須為空")
        elif self.billing_cycle == "YEARLY":
            if self.yearly_fee_usd is None or self.monthly_fee_usd is not None:
                raise ValueError("YEARLY 合約需填 yearly_fee_usd，且 monthly_fee_usd 必須為空")
        else:
            if self.monthly_fee_usd is not None or self.yearly_fee_usd is not None:
                raise ValueError("USAGE_BASED 合約不可填 monthly_fee_usd/yearly_fee_usd")

        return self


class AssetContractUpdate(BaseModel):
    billing_cycle: BillingCycle | None = None
    monthly_fee_usd: Decimal | None = None
    yearly_fee_usd: Decimal | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=16)
    start_date: date | None = None
    end_date: date | None = None
    auto_renew: bool | None = None
    payment_method: str | None = Field(default=None, max_length=64)
    status: str | None = None
    notes: str | None = Field(default=None, max_length=2000)


class AssetContractRead(BaseModel):
    id: int
    api_key_id: int | None
    ai_account_id: int | None
    billing_cycle: BillingCycle
    monthly_fee_usd: Decimal | None
    yearly_fee_usd: Decimal | None
    monthly_amortized_usd: Decimal
    currency: str
    start_date: date
    end_date: date | None
    auto_renew: bool
    payment_method: str | None
    status: str
    notes: str | None
    created_by_user_id: int | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
