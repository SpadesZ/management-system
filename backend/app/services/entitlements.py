# File Path: backend/app/services/entitlements.py
# Timestamp: 2026-05-26T22:10:00+08:00
# Version: v0.1

from dataclasses import dataclass

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.entities import ApiKeyEntitlement


@dataclass
class EntitlementCheckResult:
    allowed: bool
    reason: str | None
    matched_subjects: list[str]
    constrained_models: list[str]


def _normalize_model_code(value: str | None) -> str:
    return str(value or "").strip().lower()


def _extract_allowed_models(raw_value) -> set[str]:
    values = []

    if isinstance(raw_value, list):
        values = raw_value
    elif isinstance(raw_value, dict):
        for key in ("models", "allowed_models", "allowed_model_codes"):
            item = raw_value.get(key)
            if isinstance(item, list):
                values = item
                break

    result = set()
    for item in values:
        normalized = _normalize_model_code(str(item or ""))
        if normalized:
            result.add(normalized)
    return result


def evaluate_api_key_entitlement(
    db: Session,
    *,
    api_key_id: int,
    user_id: int,
    department_id: int,
    project_id: int | None,
    model_code: str,
) -> EntitlementCheckResult:
    active_total = db.scalar(
        select(func.count())
        .select_from(ApiKeyEntitlement)
        .where(
            ApiKeyEntitlement.api_key_id == api_key_id,
            ApiKeyEntitlement.status == "ACTIVE",
        )
    ) or 0

    # Backward compatibility: if no entitlement policy exists on this key, keep allowing requests.
    if int(active_total) <= 0:
        return EntitlementCheckResult(allowed=True, reason=None, matched_subjects=[], constrained_models=[])

    subject_filters = [
        and_(ApiKeyEntitlement.subject_type == "USER", ApiKeyEntitlement.subject_id == user_id),
        and_(ApiKeyEntitlement.subject_type == "DEPARTMENT", ApiKeyEntitlement.subject_id == department_id),
    ]
    if project_id is not None:
        subject_filters.append(
            and_(ApiKeyEntitlement.subject_type == "PROJECT", ApiKeyEntitlement.subject_id == int(project_id))
        )

    matched_rows = db.scalars(
        select(ApiKeyEntitlement).where(
            ApiKeyEntitlement.api_key_id == api_key_id,
            ApiKeyEntitlement.status == "ACTIVE",
            or_(*subject_filters),
        )
    ).all()

    if not matched_rows:
        return EntitlementCheckResult(
            allowed=False,
            reason="NO_MATCHED_SUBJECT",
            matched_subjects=[],
            constrained_models=[],
        )

    constrained_models: set[str] = set()
    matched_subjects: list[str] = []

    for row in matched_rows:
        matched_subjects.append(f"{row.subject_type}:{row.subject_id}")
        constrained_models.update(_extract_allowed_models(row.allowed_models_json))

    normalized_model = _normalize_model_code(model_code)
    if constrained_models and normalized_model not in constrained_models:
        return EntitlementCheckResult(
            allowed=False,
            reason="MODEL_NOT_ALLOWED",
            matched_subjects=sorted(set(matched_subjects)),
            constrained_models=sorted(constrained_models),
        )

    return EntitlementCheckResult(
        allowed=True,
        reason=None,
        matched_subjects=sorted(set(matched_subjects)),
        constrained_models=sorted(constrained_models),
    )
