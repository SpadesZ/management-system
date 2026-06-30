# File Path: backend/app/core/errors.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorCode:
    code: str
    message: str
    retryable: bool = False


AUTH_INVALID_CREDENTIALS = ErrorCode("AUTH_INVALID_CREDENTIALS", "Invalid email or password.")
AUTH_UNAUTHORIZED = ErrorCode("AUTH_UNAUTHORIZED", "Unauthorized.")
SCOPE_FORBIDDEN = ErrorCode("SCOPE_FORBIDDEN", "No permission for the requested scope.")
BUDGET_HARD_LIMIT_EXCEEDED = ErrorCode(
    "BUDGET_HARD_LIMIT_EXCEEDED",
    "Monthly budget hard limit exceeded.",
)
RATE_LIMIT_EXCEEDED = ErrorCode("RATE_LIMIT_EXCEEDED", "Rate limit exceeded.", retryable=True)
PROVIDER_TIMEOUT = ErrorCode("PROVIDER_TIMEOUT", "Provider timeout.", retryable=True)
MODEL_PRICE_NOT_FOUND = ErrorCode("MODEL_PRICE_NOT_FOUND", "No active model price found.")
ENTITLEMENT_DENIED = ErrorCode(
    "ENTITLEMENT_DENIED",
    "No active entitlement policy matched for this request.",
)
ENTITLEMENT_MODEL_NOT_ALLOWED = ErrorCode(
    "ENTITLEMENT_MODEL_NOT_ALLOWED",
    "The requested model is not allowed by entitlement policy.",
)
DUPLICATE_REQUEST = ErrorCode("DUPLICATE_REQUEST", "Request already processed.")
