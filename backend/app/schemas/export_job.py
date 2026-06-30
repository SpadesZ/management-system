# File Path: backend/app/schemas/export_job.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from datetime import datetime

from pydantic import BaseModel, Field


class ExportCreateRequest(BaseModel):
    export_type: str = Field(min_length=1, max_length=64)
    filters_json: dict = Field(default_factory=dict)


class ExportJobRead(BaseModel):
    id: int
    requester_user_id: int
    export_type: str
    status: str
    file_path: str | None
    expires_at: datetime | None

    class Config:
        from_attributes = True
