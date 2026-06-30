# File Path: backend/app/schemas/approval.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from pydantic import BaseModel, Field


class ApprovalRequestCreate(BaseModel):
    request_type: str = Field(min_length=1, max_length=64)
    target_type: str = Field(min_length=1, max_length=64)
    target_id: int | None = None
    reason: str = Field(min_length=3)
    payload_json: dict = Field(default_factory=dict)


class ApprovalDecisionRequest(BaseModel):
    decision_reason: str = Field(min_length=1)


class ApprovalRequestRead(BaseModel):
    id: int
    requester_id: int
    request_type: str
    target_type: str
    target_id: int | None
    reason: str
    payload_json: dict
    status: str

    class Config:
        from_attributes = True
