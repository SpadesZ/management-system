# File Path: backend/app/models/enums.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from enum import Enum


class RoleCode(str, Enum):
    ADMIN = "ADMIN"
    FINANCE = "FINANCE"
    MANAGER = "MANAGER"
    EMPLOYEE = "EMPLOYEE"
    AUDITOR = "AUDITOR"
    SECURITY = "SECURITY"


class ResourceStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DISABLED = "DISABLED"
    ARCHIVED = "ARCHIVED"


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class GatewayRequestStatus(str, Enum):
    PENDING = "PENDING"
    IN_FLIGHT = "IN_FLIGHT"
    SUCCESS = "SUCCESS"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"
    UNKNOWN_PROVIDER_STATE = "UNKNOWN_PROVIDER_STATE"
    RECONCILING = "RECONCILING"


class ReservationStatus(str, Enum):
    RESERVED = "RESERVED"
    SETTLED = "SETTLED"
    RELEASED = "RELEASED"
    PENDING_RECONCILIATION = "PENDING_RECONCILIATION"


class LedgerType(str, Enum):
    CHARGE = "CHARGE"
    ADJUSTMENT = "ADJUSTMENT"


class AlertStatus(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
