# File Path: backend/app/schemas/assistant.py
# Timestamp: 2026-05-26T12:00:00+08:00
# Version: v0.2

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "BLOCKED"]


class AssistantChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=6000)
    context_type: str = Field(default="auto", min_length=1, max_length=64)
    context_id: str | None = Field(default=None, max_length=128)
    session_id: str | None = Field(default=None, max_length=128)


class AssistantSource(BaseModel):
    source_key: str = Field(min_length=1, max_length=128)
    source_label: str = Field(min_length=1, max_length=255)
    source_id: str | None = Field(default=None, max_length=128)
    scope_checked: bool = True


class AssistantAction(BaseModel):
    action_type: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=255)
    target: str | None = Field(default=None, max_length=255)


class AssistantChatResponse(BaseModel):
    answer: str
    primary_task_id: str = Field(min_length=1, max_length=128)
    task_ids: list[str] = Field(default_factory=list)
    sources: list[AssistantSource] = Field(default_factory=list)
    risk_level: RiskLevel
    suggested_actions: list[AssistantAction] = Field(default_factory=list)
    trace_id: str = Field(min_length=1, max_length=128)
    conversation_id: int | None = None


class AssistantConversationRead(BaseModel):
    id: int
    user_id: int
    session_id: str
    intent: str
    status: str
    linked_approval_request_id: int | None
    last_risk_level: str | None
    opened_at: datetime
    last_message_at: datetime
    closed_at: datetime | None
    metadata_json: dict
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AssistantMessageRead(BaseModel):
    id: int
    conversation_id: int
    role: str
    redacted_content: str
    message_hash: str
    task_ids_json: list
    sources_json: list
    risk_level: str | None
    trace_id: str | None
    metadata_json: dict
    created_at: datetime

    class Config:
        from_attributes = True
