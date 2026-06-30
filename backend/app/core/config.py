# File Path: backend/app/core/config.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="llm-finops-v1_1")
    app_env: str = Field(default="development")
    debug: bool = Field(default=True)

    database_url: str = Field(default="postgresql+psycopg2://llm_finops:llm_finops@postgres:5432/llm_finops")
    redis_url: str = Field(default="redis://redis:6379/0")

    jwt_secret_key: str = Field(default="replace-with-strong-secret")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=480)

    master_encryption_key: str = Field(default="replace-with-32-byte-urlsafe-base64-key")
    kms_key_id: str = Field(default="local-master-key")
    kms_key_version: int = Field(default=1)

    gateway_connect_timeout_seconds: int = Field(default=5)
    gateway_provider_timeout_seconds: int = Field(default=60)
    gateway_retry_max: int = Field(default=1)
    gateway_mock_provider: bool = Field(default=True)

    default_soft_limit_usd: float = Field(default=2000)
    default_hard_limit_usd: float = Field(default=3000)
    cost_currency: str = Field(default="USD")

    default_admin_email: str = Field(default="admin@example.com")
    default_admin_name: str = Field(default="System Admin")
    default_admin_password: str = Field(default="ChangeThisPassword!")

    export_dir: str = Field(default="/app/exports")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
