# File Path: backend/app/api/routers/resource_limits.py
# Timestamp: 2026-05-26T12:00:00+08:00
# Version: v0.1

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import asc, desc, func, or_, select

from app.api.deps import CurrentUserDep, DBSessionDep, get_pagination_query, require_roles
from app.core.audit import write_audit_log
from app.models.entities import AIAccount, ApiKey, ResourceLimitState, User
from app.models.enums import RoleCode
from app.schemas.common import PaginationMeta, PaginationQuery
from app.schemas.resource_limit import ResourceLimitStateRead, ResourceLimitStateUpdate
from app.services.resource_limits import calculate_utilization_pct
from app.services.scope_filter import allowed_department_ids, get_scope_context

router = APIRouter(prefix="/resource-limits", tags=["resource-limits"])


@router.get("", response_model=dict)
def list_resource_limits(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
) -> dict:
    context = get_scope_context(current_user)
    allowed_ids = allowed_department_ids(db, context)

    stmt = (
        select(ResourceLimitState)
        .outerjoin(ApiKey, ResourceLimitState.api_key_id == ApiKey.id)
        .outerjoin(AIAccount, ResourceLimitState.ai_account_id == AIAccount.id)
        .outerjoin(User, AIAccount.owner_user_id == User.id)
    )

    if allowed_ids is not None:
        stmt = stmt.where(or_(ApiKey.department_id.in_(allowed_ids), User.department_id.in_(allowed_ids)))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    order_column = ResourceLimitState.updated_at if pagination.sort_by == "updated_at" else ResourceLimitState.id
    ordering = asc(order_column) if pagination.sort_order == "asc" else desc(order_column)

    rows = db.scalars(
        stmt.order_by(ordering)
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    ).all()

    return {
        "items": [ResourceLimitStateRead.model_validate(row).model_dump() for row in rows],
        "meta": PaginationMeta(page=pagination.page, page_size=pagination.page_size, total=int(total)).model_dump(),
    }


@router.patch("/{limit_state_id}", response_model=ResourceLimitStateRead)
def patch_resource_limit_state(
    limit_state_id: int,
    payload: ResourceLimitStateUpdate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.FINANCE.value, RoleCode.SECURITY.value)),
) -> ResourceLimitStateRead:
    entity = db.get(ResourceLimitState, limit_state_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource limit state not found")

    before = {
        "tokens_5h": entity.tokens_5h,
        "tokens_today": entity.tokens_today,
        "tokens_week": entity.tokens_week,
        "tokens_month": entity.tokens_month,
        "limit_5h": entity.limit_5h,
        "limit_day": entity.limit_day,
        "limit_week": entity.limit_week,
        "limit_month": entity.limit_month,
        "utilization_pct": str(entity.utilization_pct),
        "status": entity.status,
    }

    fields_set = payload.model_fields_set
    for field_name in [
        "tokens_5h",
        "tokens_today",
        "tokens_week",
        "tokens_month",
        "limit_5h",
        "limit_day",
        "limit_week",
        "limit_month",
    ]:
        if field_name not in fields_set:
            continue
        value = getattr(payload, field_name)
        if value is None and field_name.startswith("tokens_"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field_name} 不可為空")
        setattr(entity, field_name, value)

    if "status" in fields_set:
        if payload.status is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="status 不可為空")
        entity.status = payload.status

    entity.updated_by_user_id = actor.id
    entity.utilization_pct = calculate_utilization_pct(
        tokens_5h=entity.tokens_5h,
        tokens_today=entity.tokens_today,
        tokens_week=entity.tokens_week,
        tokens_month=entity.tokens_month,
        limit_5h=entity.limit_5h,
        limit_day=entity.limit_day,
        limit_week=entity.limit_week,
        limit_month=entity.limit_month,
    )

    db.flush()

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="RESOURCE_LIMIT_STATE_UPDATE",
        resource_type="resource_limit_states",
        resource_id=str(entity.id),
        source="API",
        ip_address=None,
        before_json=before,
        after_json={
            "tokens_5h": entity.tokens_5h,
            "tokens_today": entity.tokens_today,
            "tokens_week": entity.tokens_week,
            "tokens_month": entity.tokens_month,
            "limit_5h": entity.limit_5h,
            "limit_day": entity.limit_day,
            "limit_week": entity.limit_week,
            "limit_month": entity.limit_month,
            "utilization_pct": str(entity.utilization_pct),
            "status": entity.status,
        },
    )

    db.commit()
    db.refresh(entity)
    return ResourceLimitStateRead.model_validate(entity)
