# File Path: backend/app/schemas/lava.py
# Timestamp: 2026-05-26T00:00:00+08:00
# Version: v0.1

from pydantic import BaseModel, Field


class LavaConnectionUpdate(BaseModel):
    id: int
    name: str | None = Field(default=None, min_length=1, max_length=120)
    vendor: str = Field(default="openrouter", min_length=1, max_length=64)
    api_key: str | None = None
    model_name: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default="draft", max_length=32)
    available_models: list[dict | str] | None = None


class LavaFetchModelsRequest(BaseModel):
    vendor: str = Field(default="openrouter", min_length=1, max_length=64)
    api_key: str | None = None
    conn_id: int | None = None


class LavaConnectionTestRequest(BaseModel):
    vendor: str = Field(default="openrouter", min_length=1, max_length=64)
    api_key: str | None = None
    model_name: str | None = Field(default=None, max_length=255)
    conn_id: int | None = None


class LavaBindingUpdate(BaseModel):
    task_id: str = Field(min_length=1, max_length=128)
    connection_id: int | None = None


class LavaBindingTask(BaseModel):
    task_id: str = Field(min_length=1, max_length=128)


class LavaRuntimeCPUUpdate(BaseModel):
    cpu_cores: str = Field(min_length=1, max_length=32)


class LavaRuntimeWorkersUpdate(BaseModel):
    page_workers: int | str
