# File Path: backend/app/api/routers/ai_accounts.py
# Timestamp: 2026-05-26T21:00:00+08:00
# Version: v0.2

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc, func, select

from app.api.deps import CurrentUserDep, DBSessionDep, get_pagination_query, require_roles
from app.core.audit import write_audit_log
from app.core.config import get_settings
from app.core.security import security_manager
from app.models.entities import (
    AIAccount,
    AIAccountAccessGrant,
    AIAccountAssignment,
    AIAccountCredential,
    AIAccountHistory,
    User,
)
from app.models.enums import ResourceStatus, RoleCode
from app.schemas.ai_account import (
    AIAccountAccessGrantCreate,
    AIAccountAccessGrantRead,
    AIAccountAccessGrantRevokeRequest,
    AIAccountAssignmentRequest,
    AIAccountCreate,
    AIAccountCredentialCreate,
    AIAccountCredentialRead,
    AIAccountCredentialRotateRequest,
    AIAccountHistoryRead,
    AIAccountRead,
    AIAccountUpdate,
)
from app.schemas.common import PaginationMeta, PaginationQuery
from app.services.masking import mask_api_key
from app.services.scope_filter import allowed_department_ids, ensure_resource_scope, get_scope_context

router = APIRouter(prefix="/ai-accounts", tags=["ai-accounts"])

ALLOWED_ACCOUNT_STATUS = {
    ResourceStatus.ACTIVE.value,
    ResourceStatus.INACTIVE.value,
    ResourceStatus.DISABLED.value,
    ResourceStatus.ARCHIVED.value,
}


def _normalized_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Text field cannot be empty")
    return normalized


def _resolve_user_or_404(db: DBSessionDep, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _resolve_account_or_404(db: DBSessionDep, account_id: int) -> AIAccount:
    account = db.get(AIAccount, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI account not found")
    return account


def _assert_user_scope_or_403(db: DBSessionDep, actor: User, target_user_id: int) -> User:
    context = get_scope_context(actor)
    allowed_ids = allowed_department_ids(db, context)
    target_user = _resolve_user_or_404(db, target_user_id)
    if not ensure_resource_scope(int(target_user.department_id), allowed_ids):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission for this department scope")
    return target_user


def _assert_account_scope_or_403(db: DBSessionDep, actor: User, account: AIAccount) -> User:
    return _assert_user_scope_or_403(db, actor, int(account.owner_user_id))


def _assert_account_status(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in ALLOWED_ACCOUNT_STATUS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid account status")
    return normalized


def _append_history(
    db: DBSessionDep,
    *,
    account_id: int,
    event_type: str,
    actor_user_id: int | None,
    detail_json: dict,
) -> None:
    db.add(
        AIAccountHistory(
            ai_account_id=account_id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            detail_json=detail_json,
        )
    )


def _create_access_grant(
    db: DBSessionDep,
    *,
    account_id: int,
    user_id: int,
    granted_by_user_id: int | None,
    grant_reason: str | None,
) -> AIAccountAccessGrant:
    existing = db.scalar(
        select(AIAccountAccessGrant).where(
            AIAccountAccessGrant.ai_account_id == account_id,
            AIAccountAccessGrant.user_id == user_id,
            AIAccountAccessGrant.status == "ACTIVE",
        )
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Access grant already exists")

    grant = AIAccountAccessGrant(
        ai_account_id=account_id,
        user_id=user_id,
        granted_by_user_id=granted_by_user_id,
        grant_reason=grant_reason,
        status="ACTIVE",
    )
    db.add(grant)

    legacy = AIAccountAssignment(
        ai_account_id=account_id,
        user_id=user_id,
        status="ACTIVE",
    )
    db.add(legacy)

    db.flush()
    return grant


def _revoke_access_grant(
    db: DBSessionDep,
    *,
    grant: AIAccountAccessGrant,
    revoked_by_user_id: int | None,
    revoke_reason: str | None,
) -> None:
    if grant.status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Access grant is not active")

    now = datetime.now(UTC)
    grant.status = "REVOKED"
    grant.revoked_by_user_id = revoked_by_user_id
    grant.revoke_reason = revoke_reason
    grant.revoked_at = now

    legacy = db.scalar(
        select(AIAccountAssignment)
        .where(
            AIAccountAssignment.ai_account_id == grant.ai_account_id,
            AIAccountAssignment.user_id == grant.user_id,
            AIAccountAssignment.status == "ACTIVE",
        )
        .order_by(desc(AIAccountAssignment.assigned_at))
    )
    if legacy is not None:
        legacy.status = "INACTIVE"
        legacy.revoked_at = now

    db.flush()


@router.get("", response_model=dict)
def list_ai_accounts(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
) -> dict:
    context = get_scope_context(current_user)
    allowed_ids = allowed_department_ids(db, context)

    owner_departments = select(User.id.label("owner_user_id"), User.department_id.label("owner_department_id")).subquery()
    stmt = select(AIAccount).join(owner_departments, owner_departments.c.owner_user_id == AIAccount.owner_user_id)

    if allowed_ids is not None:
        stmt = stmt.where(owner_departments.c.owner_department_id.in_(allowed_ids))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    order_column = AIAccount.created_at if pagination.sort_by == "created_at" else AIAccount.id
    ordering = asc(order_column) if pagination.sort_order == "asc" else desc(order_column)
    rows = db.scalars(
        stmt.order_by(ordering)
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    ).all()

    return {
        "items": [AIAccountRead.model_validate(row).model_dump() for row in rows],
        "meta": PaginationMeta(page=pagination.page, page_size=pagination.page_size, total=int(total)).model_dump(),
    }


@router.post("", response_model=AIAccountRead)
def create_ai_account(
    payload: AIAccountCreate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.FINANCE.value)),
) -> AIAccountRead:
    owner_user = _assert_user_scope_or_403(db, actor, int(payload.owner_user_id))
    if owner_user.status != ResourceStatus.ACTIVE.value:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Owner user is not active")

    account = AIAccount(
        vendor=_normalized_text(payload.vendor),
        product=_normalized_text(payload.product),
        plan=_normalized_text(payload.plan),
        seats=payload.seats,
        monthly_cost_usd=payload.monthly_cost_usd,
        renewal_date=payload.renewal_date,
        owner_user_id=payload.owner_user_id,
        status=_assert_account_status(payload.status),
    )
    db.add(account)
    db.flush()

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="AI_ACCOUNT_CREATE",
        resource_type="ai_accounts",
        resource_id=str(account.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={
            "vendor": account.vendor,
            "product": account.product,
            "plan": account.plan,
            "owner_user_id": account.owner_user_id,
            "status": account.status,
        },
    )
    _append_history(
        db,
        account_id=account.id,
        event_type="ACCOUNT_CREATE",
        actor_user_id=actor.id,
        detail_json={
            "vendor": account.vendor,
            "product": account.product,
            "plan": account.plan,
            "owner_user_id": account.owner_user_id,
            "owner_department_id": int(owner_user.department_id),
        },
    )

    db.commit()
    db.refresh(account)
    return AIAccountRead.model_validate(account)


@router.patch("/{account_id}", response_model=AIAccountRead)
def patch_ai_account(
    account_id: int,
    payload: AIAccountUpdate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.FINANCE.value)),
) -> AIAccountRead:
    account = _resolve_account_or_404(db, account_id)
    _assert_account_scope_or_403(db, actor, account)

    before = {
        "plan": account.plan,
        "seats": account.seats,
        "monthly_cost_usd": str(account.monthly_cost_usd),
        "renewal_date": account.renewal_date.isoformat() if account.renewal_date else None,
        "owner_user_id": account.owner_user_id,
        "status": account.status,
    }

    if payload.plan is not None:
        account.plan = _normalized_text(payload.plan)
    if payload.seats is not None:
        account.seats = payload.seats
    if payload.monthly_cost_usd is not None:
        if payload.monthly_cost_usd < 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="monthly_cost_usd cannot be negative")
        account.monthly_cost_usd = payload.monthly_cost_usd
    if payload.renewal_date is not None:
        account.renewal_date = payload.renewal_date
    if payload.owner_user_id is not None:
        owner = _assert_user_scope_or_403(db, actor, int(payload.owner_user_id))
        if owner.status != ResourceStatus.ACTIVE.value:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Owner user is not active")
        account.owner_user_id = payload.owner_user_id
    if payload.status is not None:
        account.status = _assert_account_status(payload.status)

    db.flush()

    after = {
        "plan": account.plan,
        "seats": account.seats,
        "monthly_cost_usd": str(account.monthly_cost_usd),
        "renewal_date": account.renewal_date.isoformat() if account.renewal_date else None,
        "owner_user_id": account.owner_user_id,
        "status": account.status,
    }

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="AI_ACCOUNT_UPDATE",
        resource_type="ai_accounts",
        resource_id=str(account.id),
        source="API",
        ip_address=None,
        before_json=before,
        after_json=after,
    )
    _append_history(
        db,
        account_id=account.id,
        event_type="ACCOUNT_UPDATE",
        actor_user_id=actor.id,
        detail_json={"before": before, "after": after},
    )

    db.commit()
    db.refresh(account)
    return AIAccountRead.model_validate(account)


@router.get("/{account_id}/credentials", response_model=dict)
def list_ai_account_credentials(
    account_id: int,
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
) -> dict:
    account = _resolve_account_or_404(db, account_id)
    _assert_account_scope_or_403(db, current_user, account)

    stmt = select(AIAccountCredential).where(AIAccountCredential.ai_account_id == account_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    if pagination.sort_by == "created_at":
        order_column = AIAccountCredential.created_at
    elif pagination.sort_by == "status":
        order_column = AIAccountCredential.status
    else:
        order_column = AIAccountCredential.id

    ordering = asc(order_column) if pagination.sort_order == "asc" else desc(order_column)

    rows = db.scalars(
        stmt.order_by(ordering)
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    ).all()

    return {
        "items": [AIAccountCredentialRead.model_validate(row).model_dump(mode="json") for row in rows],
        "meta": PaginationMeta(page=pagination.page, page_size=pagination.page_size, total=int(total)).model_dump(),
    }


@router.post("/{account_id}/credentials", response_model=AIAccountCredentialRead)
def create_ai_account_credential(
    account_id: int,
    payload: AIAccountCredentialCreate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.SECURITY.value)),
) -> AIAccountCredentialRead:
    account = _resolve_account_or_404(db, account_id)
    _assert_account_scope_or_403(db, actor, account)

    credential_name = _normalized_text(payload.credential_name)
    existing = db.scalar(
        select(AIAccountCredential).where(
            AIAccountCredential.ai_account_id == account.id,
            AIAccountCredential.credential_name == credential_name,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Credential name already exists")

    settings = get_settings()
    encrypted = security_manager.envelope_encrypt_api_key(payload.plain_secret)
    credential = AIAccountCredential(
        ai_account_id=account.id,
        credential_name=credential_name,
        credential_type=payload.credential_type,
        encrypted_secret=encrypted.encrypted_secret,
        encrypted_dek=encrypted.encrypted_dek,
        kms_key_id=settings.kms_key_id,
        key_version=settings.kms_key_version,
        masked_secret=mask_api_key(payload.plain_secret),
        status=ResourceStatus.ACTIVE.value,
        expires_at=payload.expires_at,
        created_by_user_id=actor.id,
    )
    db.add(credential)
    db.flush()

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="AI_ACCOUNT_CREDENTIAL_CREATE",
        resource_type="ai_account_credentials",
        resource_id=str(credential.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={
            "ai_account_id": account.id,
            "credential_name": credential.credential_name,
            "credential_type": credential.credential_type,
            "masked_secret": credential.masked_secret,
            "status": credential.status,
        },
        metadata_json={"key_version": credential.key_version, "kms_key_id": credential.kms_key_id},
    )
    _append_history(
        db,
        account_id=account.id,
        event_type="CREDENTIAL_CREATE",
        actor_user_id=actor.id,
        detail_json={
            "credential_id": credential.id,
            "credential_name": credential.credential_name,
            "credential_type": credential.credential_type,
            "status": credential.status,
        },
    )

    db.commit()
    db.refresh(credential)
    return AIAccountCredentialRead.model_validate(credential)


@router.post("/{account_id}/credentials/{credential_id}/rotate", response_model=AIAccountCredentialRead)
def rotate_ai_account_credential(
    account_id: int,
    credential_id: int,
    payload: AIAccountCredentialRotateRequest,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.SECURITY.value)),
) -> AIAccountCredentialRead:
    account = _resolve_account_or_404(db, account_id)
    _assert_account_scope_or_403(db, actor, account)

    credential = db.get(AIAccountCredential, credential_id)
    if credential is None or int(credential.ai_account_id) != int(account.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")
    if credential.status != ResourceStatus.ACTIVE.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only active credential can be rotated")

    before = {
        "masked_secret": credential.masked_secret,
        "last_rotated_at": credential.last_rotated_at.isoformat() if credential.last_rotated_at else None,
    }

    encrypted = security_manager.envelope_encrypt_api_key(payload.new_plain_secret)
    credential.encrypted_secret = encrypted.encrypted_secret
    credential.encrypted_dek = encrypted.encrypted_dek
    credential.masked_secret = mask_api_key(payload.new_plain_secret)
    credential.last_rotated_at = datetime.now(UTC)
    db.flush()

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="AI_ACCOUNT_CREDENTIAL_ROTATE",
        resource_type="ai_account_credentials",
        resource_id=str(credential.id),
        source="API",
        ip_address=None,
        before_json=before,
        after_json={
            "masked_secret": credential.masked_secret,
            "last_rotated_at": credential.last_rotated_at.isoformat() if credential.last_rotated_at else None,
        },
        metadata_json={"key_version": credential.key_version, "kms_key_id": credential.kms_key_id},
    )
    _append_history(
        db,
        account_id=account.id,
        event_type="CREDENTIAL_ROTATE",
        actor_user_id=actor.id,
        detail_json={
            "credential_id": credential.id,
            "credential_name": credential.credential_name,
            "last_rotated_at": credential.last_rotated_at.isoformat() if credential.last_rotated_at else None,
        },
    )

    db.commit()
    db.refresh(credential)
    return AIAccountCredentialRead.model_validate(credential)


@router.post("/{account_id}/credentials/{credential_id}/disable", response_model=AIAccountCredentialRead)
def disable_ai_account_credential(
    account_id: int,
    credential_id: int,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.SECURITY.value)),
) -> AIAccountCredentialRead:
    account = _resolve_account_or_404(db, account_id)
    _assert_account_scope_or_403(db, actor, account)

    credential = db.get(AIAccountCredential, credential_id)
    if credential is None or int(credential.ai_account_id) != int(account.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")

    if credential.status == ResourceStatus.DISABLED.value:
        return AIAccountCredentialRead.model_validate(credential)

    credential.status = ResourceStatus.DISABLED.value
    db.flush()

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="AI_ACCOUNT_CREDENTIAL_DISABLE",
        resource_type="ai_account_credentials",
        resource_id=str(credential.id),
        source="API",
        ip_address=None,
        before_json={"status": ResourceStatus.ACTIVE.value},
        after_json={"status": credential.status},
    )
    _append_history(
        db,
        account_id=account.id,
        event_type="CREDENTIAL_DISABLE",
        actor_user_id=actor.id,
        detail_json={"credential_id": credential.id, "credential_name": credential.credential_name},
    )

    db.commit()
    db.refresh(credential)
    return AIAccountCredentialRead.model_validate(credential)


@router.get("/{account_id}/access-grants", response_model=dict)
def list_ai_account_access_grants(
    account_id: int,
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
) -> dict:
    account = _resolve_account_or_404(db, account_id)
    _assert_account_scope_or_403(db, current_user, account)

    stmt = select(AIAccountAccessGrant).where(AIAccountAccessGrant.ai_account_id == account_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    if pagination.sort_by == "granted_at":
        order_column = AIAccountAccessGrant.granted_at
    elif pagination.sort_by == "status":
        order_column = AIAccountAccessGrant.status
    else:
        order_column = AIAccountAccessGrant.id

    ordering = asc(order_column) if pagination.sort_order == "asc" else desc(order_column)
    rows = db.scalars(
        stmt.order_by(ordering)
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    ).all()

    return {
        "items": [AIAccountAccessGrantRead.model_validate(row).model_dump(mode="json") for row in rows],
        "meta": PaginationMeta(page=pagination.page, page_size=pagination.page_size, total=int(total)).model_dump(),
    }


@router.post("/{account_id}/access-grants", response_model=AIAccountAccessGrantRead)
def create_ai_account_access_grant(
    account_id: int,
    payload: AIAccountAccessGrantCreate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.MANAGER.value)),
) -> AIAccountAccessGrantRead:
    account = _resolve_account_or_404(db, account_id)
    _assert_account_scope_or_403(db, actor, account)

    grantee = _assert_user_scope_or_403(db, actor, int(payload.user_id))
    if grantee.status != ResourceStatus.ACTIVE.value:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Granted user is not active")

    grant = _create_access_grant(
        db,
        account_id=account.id,
        user_id=payload.user_id,
        granted_by_user_id=actor.id,
        grant_reason=payload.grant_reason,
    )

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="AI_ACCOUNT_ACCESS_GRANT",
        resource_type="ai_account_access_grants",
        resource_id=str(grant.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={
            "ai_account_id": grant.ai_account_id,
            "user_id": grant.user_id,
            "status": grant.status,
            "grant_reason": grant.grant_reason,
        },
    )
    _append_history(
        db,
        account_id=account.id,
        event_type="ACCESS_GRANT",
        actor_user_id=actor.id,
        detail_json={
            "grant_id": grant.id,
            "user_id": grant.user_id,
            "grantee_department_id": int(grantee.department_id),
            "grant_reason": grant.grant_reason,
        },
    )

    db.commit()
    db.refresh(grant)
    return AIAccountAccessGrantRead.model_validate(grant)


@router.post("/{account_id}/access-grants/{grant_id}/revoke", response_model=AIAccountAccessGrantRead)
def revoke_ai_account_access_grant(
    account_id: int,
    grant_id: int,
    payload: AIAccountAccessGrantRevokeRequest,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.MANAGER.value)),
) -> AIAccountAccessGrantRead:
    account = _resolve_account_or_404(db, account_id)
    _assert_account_scope_or_403(db, actor, account)

    grant = db.get(AIAccountAccessGrant, grant_id)
    if grant is None or int(grant.ai_account_id) != int(account.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access grant not found")

    _revoke_access_grant(
        db,
        grant=grant,
        revoked_by_user_id=actor.id,
        revoke_reason=payload.revoke_reason,
    )

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="AI_ACCOUNT_ACCESS_REVOKE",
        resource_type="ai_account_access_grants",
        resource_id=str(grant.id),
        source="API",
        ip_address=None,
        before_json={"status": "ACTIVE"},
        after_json={
            "status": grant.status,
            "revoked_at": grant.revoked_at.isoformat() if grant.revoked_at else None,
            "revoke_reason": grant.revoke_reason,
        },
    )
    _append_history(
        db,
        account_id=account.id,
        event_type="ACCESS_REVOKE",
        actor_user_id=actor.id,
        detail_json={
            "grant_id": grant.id,
            "user_id": grant.user_id,
            "revoke_reason": grant.revoke_reason,
            "revoked_at": grant.revoked_at.isoformat() if grant.revoked_at else None,
        },
    )

    db.commit()
    db.refresh(grant)
    return AIAccountAccessGrantRead.model_validate(grant)


@router.get("/{account_id}/history", response_model=dict)
def list_ai_account_history(
    account_id: int,
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
    event_type: str | None = Query(default=None, max_length=64),
) -> dict:
    account = _resolve_account_or_404(db, account_id)
    _assert_account_scope_or_403(db, current_user, account)

    stmt = select(AIAccountHistory).where(AIAccountHistory.ai_account_id == account_id)
    normalized_event_type = str(event_type or "").strip().upper()
    if normalized_event_type:
        stmt = stmt.where(AIAccountHistory.event_type == normalized_event_type)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    order_column = AIAccountHistory.event_time if pagination.sort_by == "event_time" else AIAccountHistory.id
    ordering = asc(order_column) if pagination.sort_order == "asc" else desc(order_column)
    rows = db.scalars(
        stmt.order_by(ordering)
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    ).all()

    return {
        "items": [AIAccountHistoryRead.model_validate(row).model_dump(mode="json") for row in rows],
        "meta": PaginationMeta(page=pagination.page, page_size=pagination.page_size, total=int(total)).model_dump(),
    }


@router.post("/{account_id}/assign", response_model=dict)
def assign_ai_account(
    account_id: int,
    payload: AIAccountAssignmentRequest,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.MANAGER.value)),
) -> dict:
    account = _resolve_account_or_404(db, account_id)
    _assert_account_scope_or_403(db, actor, account)
    grantee = _assert_user_scope_or_403(db, actor, int(payload.user_id))

    grant = _create_access_grant(
        db,
        account_id=account.id,
        user_id=payload.user_id,
        granted_by_user_id=actor.id,
        grant_reason="legacy_assign_endpoint",
    )

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="AI_ACCOUNT_ASSIGN",
        resource_type="ai_account_assignments",
        resource_id=str(grant.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={"ai_account_id": account.id, "user_id": payload.user_id},
    )
    _append_history(
        db,
        account_id=account.id,
        event_type="ACCESS_GRANT",
        actor_user_id=actor.id,
        detail_json={
            "grant_id": grant.id,
            "user_id": grant.user_id,
            "grantee_department_id": int(grantee.department_id),
            "source": "legacy_assign_endpoint",
        },
    )

    db.commit()
    return {"message": "assigned", "assignment_id": grant.id}


@router.post("/{account_id}/revoke", response_model=dict)
def revoke_ai_account(
    account_id: int,
    payload: AIAccountAssignmentRequest,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.MANAGER.value)),
) -> dict:
    account = _resolve_account_or_404(db, account_id)
    _assert_account_scope_or_403(db, actor, account)

    grant = db.scalar(
        select(AIAccountAccessGrant)
        .where(
            AIAccountAccessGrant.ai_account_id == account_id,
            AIAccountAccessGrant.user_id == payload.user_id,
            AIAccountAccessGrant.status == "ACTIVE",
        )
        .order_by(desc(AIAccountAccessGrant.granted_at))
    )
    if grant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")

    _revoke_access_grant(
        db,
        grant=grant,
        revoked_by_user_id=actor.id,
        revoke_reason="legacy_revoke_endpoint",
    )

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="AI_ACCOUNT_REVOKE",
        resource_type="ai_account_assignments",
        resource_id=str(grant.id),
        source="API",
        ip_address=None,
        before_json={"status": "ACTIVE"},
        after_json={"status": grant.status, "revoked_at": grant.revoked_at.isoformat() if grant.revoked_at else None},
    )
    _append_history(
        db,
        account_id=account.id,
        event_type="ACCESS_REVOKE",
        actor_user_id=actor.id,
        detail_json={
            "grant_id": grant.id,
            "user_id": grant.user_id,
            "revoke_reason": "legacy_revoke_endpoint",
            "revoked_at": grant.revoked_at.isoformat() if grant.revoked_at else None,
        },
    )

    db.commit()
    return {"message": "revoked", "assignment_id": grant.id}
