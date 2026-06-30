# File Path: backend/app/core/audit.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import AuditLog


def write_audit_log(
    db: Session,
    *,
    actor_user_id: int | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    source: str,
    ip_address: str | None,
    before_json: dict[str, Any] | None,
    after_json: dict[str, Any] | None,
    metadata_json: dict[str, Any] | None = None,
) -> None:
    log = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        source=source,
        ip_address=ip_address,
        before_json=before_json,
        after_json=after_json,
        metadata_json=metadata_json or {},
    )
    db.add(log)
