# File Path: backend/app/schemas/common.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from datetime import datetime

from pydantic import BaseModel, Field


class APIMessage(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    request_id: str
    error_code: str
    message: str
    retryable: bool = False


class PaginationQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)
    sort_by: str = Field(default="id")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")
    start_at: datetime | None = None
    end_at: datetime | None = None
    timezone: str = Field(default="UTC")


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int


class ListResponse(BaseModel):
    items: list
    meta: PaginationMeta
