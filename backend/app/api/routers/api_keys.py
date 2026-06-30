# File Path: backend/app/api/routers/api_keys.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import asc, desc, func, select

from app.api.deps import CurrentUserDep, DBSessionDep, get_pagination_query, require_roles
from app.core.audit import write_audit_log
from app.core.config import get_settings
from app.core.security import security_manager
from app.models.entities import ApiKey, Provider, User
from app.models.enums import RoleCode
from app.schemas.api_key import APIKeyCreate, APIKeyDisableRequest, APIKeyRead, APIKeyRotateRequest, APIKeyUpdate
from app.schemas.common import PaginationMeta, PaginationQuery
from app.services.masking import mask_api_key
from app.services.scope_filter import allowed_department_ids, get_scope_context

router = APIRouter(prefix="/api-keys", tags=["api-keys"])

ALLOWED_API_KEY_STATUS = {"ACTIVE", "INACTIVE", "DISABLED", "ARCHIVED"}


def _normalize_reason(value: str | None, *, field_name: str) -> str:
    reason = str(value or "").strip()
    if not reason:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} is required",
        )
    return reason


def _validate_owner_department(db: DBSessionDep, *, owner_user_id: int, department_id: int) -> User:
    owner = db.get(User, owner_user_id)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid owner_user_id")
    if int(owner.department_id) != int(department_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="owner_user_id must belong to department_id",
        )
    return owner


def _validate_provider_active(db: DBSessionDep, provider_id: int) -> Provider:
    provider = db.get(Provider, provider_id)
    if provider is None or provider.status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid provider_id")
    return provider


def _validate_key_schedule(expires_at, rotation_due_at) -> None:
    now = datetime.now(UTC)
    if expires_at is not None and expires_at <= now:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="expires_at must be in the future")
    if rotation_due_at is not None and rotation_due_at <= now:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="rotation_due_at must be in the future",
        )
    if expires_at is not None and rotation_due_at is not None and rotation_due_at > expires_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="rotation_due_at must not be later than expires_at",
        )


@router.get("", response_model=dict)
def list_api_keys(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
) -> dict:
    context = get_scope_context(current_user)
    allowed_ids = allowed_department_ids(db, context)

    stmt = select(ApiKey)
    if allowed_ids is not None:
        stmt = stmt.where(ApiKey.department_id.in_(allowed_ids))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    order_column = ApiKey.created_at if pagination.sort_by == "created_at" else ApiKey.id
    ordering = asc(order_column) if pagination.sort_order == "asc" else desc(order_column)

    rows = db.scalars(
        stmt.order_by(ordering)
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    ).all()

    return {
        "items": [APIKeyRead.model_validate(row).model_dump() for row in rows],
        "meta": PaginationMeta(page=pagination.page, page_size=pagination.page_size, total=int(total)).model_dump(),
    }


@router.post("", response_model=APIKeyRead)
def create_api_key(
    payload: APIKeyCreate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.SECURITY.value)),
) -> APIKeyRead:
    _validate_provider_active(db, payload.provider_id)
    _validate_owner_department(db, owner_user_id=payload.owner_user_id, department_id=payload.department_id)
    _validate_key_schedule(payload.expires_at, payload.rotation_due_at)

    settings = get_settings()
    encrypted = security_manager.envelope_encrypt_api_key(payload.plain_secret)

    if payload.is_primary:
        existing_primary_rows = db.scalars(
            select(ApiKey).where(
                ApiKey.provider_id == payload.provider_id,
                ApiKey.department_id == payload.department_id,
                ApiKey.status == "ACTIVE",
                ApiKey.is_primary.is_(True),
            )
        ).all()
        for existing in existing_primary_rows:
            existing.is_primary = False

    entity = ApiKey(
        provider_id=payload.provider_id,
        name=payload.name,
        encrypted_secret=encrypted.encrypted_secret,
        encrypted_dek=encrypted.encrypted_dek,
        kms_key_id=settings.kms_key_id,
        key_version=settings.kms_key_version,
        masked_key=mask_api_key(payload.plain_secret),
        owner_user_id=payload.owner_user_id,
        department_id=payload.department_id,
        status="ACTIVE",
        expires_at=payload.expires_at,
        rotation_due_at=payload.rotation_due_at,
        is_primary=payload.is_primary,
    )
    db.add(entity)
    db.flush()

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="API_KEY_CREATE",
        resource_type="api_keys",
        resource_id=str(entity.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={
            "provider_id": entity.provider_id,
            "name": entity.name,
            "owner_user_id": entity.owner_user_id,
            "department_id": entity.department_id,
            "masked_key": entity.masked_key,
        },
        metadata_json={"key_version": entity.key_version, "kms_key_id": entity.kms_key_id},
    )

    db.commit()
    db.refresh(entity)
    return APIKeyRead.model_validate(entity)


@router.patch("/{api_key_id}", response_model=APIKeyRead)
def patch_api_key(
    api_key_id: int,
    payload: APIKeyUpdate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.SECURITY.value)),
) -> APIKeyRead:
    entity = db.get(ApiKey, api_key_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    before = {
        "name": entity.name,
        "owner_user_id": entity.owner_user_id,
        "department_id": entity.department_id,
        "status": entity.status,
        "expires_at": entity.expires_at.isoformat() if entity.expires_at else None,
    }

    if payload.status is not None:
        normalized_status = str(payload.status).strip().upper()
        if normalized_status not in ALLOWED_API_KEY_STATUS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid status")
        if normalized_status == "DISABLED":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Use /api-keys/{api_key_id}/disable for disable operation",
            )
        entity.status = normalized_status

    if payload.name is not None:
        entity.name = payload.name

    target_owner_user_id = int(payload.owner_user_id) if payload.owner_user_id is not None else int(entity.owner_user_id)
    target_department_id = int(payload.department_id) if payload.department_id is not None else int(entity.department_id)
    _validate_owner_department(db, owner_user_id=target_owner_user_id, department_id=target_department_id)

    entity.owner_user_id = target_owner_user_id
    entity.department_id = target_department_id

    if payload.expires_at is not None:
        entity.expires_at = payload.expires_at
    if payload.rotation_due_at is not None:
        entity.rotation_due_at = payload.rotation_due_at

    _validate_key_schedule(entity.expires_at, entity.rotation_due_at)

    db.flush()

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="API_KEY_UPDATE",
        resource_type="api_keys",
        resource_id=str(entity.id),
        source="API",
        ip_address=None,
        before_json=before,
        after_json={
            "name": entity.name,
            "owner_user_id": entity.owner_user_id,
            "department_id": entity.department_id,
            "status": entity.status,
            "expires_at": entity.expires_at.isoformat() if entity.expires_at else None,
        },
    )

    db.commit()
    db.refresh(entity)
    return APIKeyRead.model_validate(entity)


@router.post("/{api_key_id}/rotate", response_model=APIKeyRead)
def rotate_api_key(
    api_key_id: int,
    payload: APIKeyRotateRequest,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.SECURITY.value)),
) -> APIKeyRead:
    entity = db.get(ApiKey, api_key_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    if entity.status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only ACTIVE API key can be rotated")

    now = datetime.now(UTC)
    if entity.expires_at is not None and entity.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Expired API key cannot be rotated")

    rotation_reason = _normalize_reason(payload.reason, field_name="reason")

    encrypted = security_manager.envelope_encrypt_api_key(payload.new_plain_secret)
    entity.encrypted_secret = encrypted.encrypted_secret
    entity.encrypted_dek = encrypted.encrypted_dek
    entity.masked_key = mask_api_key(payload.new_plain_secret)
    previous_version = int(entity.key_version)
    entity.key_version = previous_version + 1
    entity.last_rotated_at = now
    entity.rotation_due_at = now + timedelta(days=90)

    db.flush()

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="API_KEY_ROTATE",
        resource_type="api_keys",
        resource_id=str(entity.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={"masked_key": entity.masked_key, "last_rotated_at": entity.last_rotated_at.isoformat()},
        metadata_json={
            "key_version": entity.key_version,
            "previous_key_version": previous_version,
            "rotation_reason": rotation_reason,
        },
    )

    db.commit()
    db.refresh(entity)
    return APIKeyRead.model_validate(entity)


@router.post("/{api_key_id}/disable", response_model=APIKeyRead)
def disable_api_key(
    api_key_id: int,
    payload: APIKeyDisableRequest,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.SECURITY.value)),
) -> APIKeyRead:
    entity = db.get(ApiKey, api_key_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    if entity.status == "DISABLED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="API key already disabled")

    disable_reason = _normalize_reason(payload.reason, field_name="reason")

    replacement_key = db.scalar(
        select(ApiKey)
        .where(
            ApiKey.provider_id == entity.provider_id,
            ApiKey.department_id == entity.department_id,
            ApiKey.status == "ACTIVE",
            ApiKey.id != entity.id,
        )
        .order_by(ApiKey.is_primary.desc(), ApiKey.id.asc())
    )
    if entity.status == "ACTIVE" and replacement_key is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot disable the last active API key for this provider and department",
        )

    entity.status = "DISABLED"
    entity.is_primary = False
    if replacement_key is not None and not bool(replacement_key.is_primary):
        replacement_key.is_primary = True

    db.flush()

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="API_KEY_DISABLE",
        resource_type="api_keys",
        resource_id=str(entity.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={
            "status": entity.status,
            "replacement_key_id": int(replacement_key.id) if replacement_key is not None else None,
        },
        metadata_json={"disable_reason": disable_reason},
    )

    db.commit()
    db.refresh(entity)
    return APIKeyRead.model_validate(entity)
