# File Path: backend/app/api/routers/resource_usage_events.py
# Timestamp: 2026-05-26T12:00:00+08:00
# Version: v0.1

from datetime import UTC, datetime

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import asc, desc, func, select

from app.api.deps import CurrentUserDep, DBSessionDep, get_pagination_query, require_roles
from app.core.audit import write_audit_log
from app.models.entities import AIAccount, ApiKey, ResourceUsageEvent, User
from app.models.enums import RoleCode
from app.schemas.common import PaginationMeta, PaginationQuery
from app.schemas.resource_usage_event import ResourceUsageEventCreate, ResourceUsageEventRead
from app.services.resource_limits import recompute_limit_state
from app.services.scope_filter import (
    allowed_department_ids,
    apply_department_scope,
    ensure_resource_scope,
    get_scope_context,
)

router = APIRouter(prefix="/resource-usage-events", tags=["resource-usage-events"])


@router.get("", response_model=dict)
def list_resource_usage_events(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
) -> dict:
    context = get_scope_context(current_user)
    allowed_ids = allowed_department_ids(db, context)

    start_at = pagination.start_at or datetime(datetime.now(UTC).year, datetime.now(UTC).month, 1, tzinfo=UTC)
    end_at = pagination.end_at or (start_at + relativedelta(months=1))

    stmt = select(ResourceUsageEvent).where(
        ResourceUsageEvent.occurred_at >= start_at,
        ResourceUsageEvent.occurred_at < end_at,
    )
    stmt = apply_department_scope(stmt, ResourceUsageEvent.department_id, allowed_ids)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    order_column = ResourceUsageEvent.occurred_at if pagination.sort_by == "occurred_at" else ResourceUsageEvent.id
    ordering = asc(order_column) if pagination.sort_order == "asc" else desc(order_column)

    rows = db.scalars(
        stmt.order_by(ordering)
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    ).all()

    return {
        "items": [ResourceUsageEventRead.model_validate(row).model_dump() for row in rows],
        "meta": PaginationMeta(page=pagination.page, page_size=pagination.page_size, total=int(total)).model_dump(),
    }


@router.post("", response_model=ResourceUsageEventRead)
def create_resource_usage_event(
    payload: ResourceUsageEventCreate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.FINANCE.value, RoleCode.MANAGER.value)),
) -> ResourceUsageEventRead:
    if payload.external_event_id:
        duplicated = db.scalar(
            select(ResourceUsageEvent).where(
                ResourceUsageEvent.event_source == payload.event_source,
                ResourceUsageEvent.external_event_id == payload.external_event_id,
            )
        )
        if duplicated is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="external_event_id already exists")

    api_key_id = payload.api_key_id
    ai_account_id = payload.ai_account_id
    resolved_department_id = payload.department_id

    if api_key_id is not None:
        api_key = db.get(ApiKey, api_key_id)
        if api_key is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
        resolved_department_id = int(api_key.department_id)
    else:
        ai_account = db.get(AIAccount, ai_account_id)
        if ai_account is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI account not found")
        if resolved_department_id is None:
            owner = db.get(User, ai_account.owner_user_id)
            resolved_department_id = int(owner.department_id) if owner is not None else None

    context = get_scope_context(actor)
    allowed_ids = allowed_department_ids(db, context)
    if not ensure_resource_scope(resolved_department_id, allowed_ids):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission for this department scope")

    actor_user_id = payload.actor_user_id
    if actor_user_id is not None and actor.role not in {RoleCode.ADMIN.value, RoleCode.FINANCE.value}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only ADMIN/FINANCE can override actor_user_id")

    total_tokens = payload.total_tokens if payload.total_tokens is not None else payload.input_tokens + payload.output_tokens

    event = ResourceUsageEvent(
        api_key_id=api_key_id,
        ai_account_id=ai_account_id,
        department_id=resolved_department_id,
        project_id=payload.project_id,
        actor_user_id=actor_user_id or actor.id,
        request_id=payload.request_id,
        event_source=payload.event_source,
        external_event_id=payload.external_event_id,
        input_tokens=payload.input_tokens,
        output_tokens=payload.output_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=payload.estimated_cost_usd,
        currency=payload.currency,
        occurred_at=payload.occurred_at,
        metadata_json=payload.metadata_json,
    )
    db.add(event)
    db.flush()

    recompute_limit_state(
        db,
        api_key_id=api_key_id,
        ai_account_id=ai_account_id,
        updated_by_user_id=actor.id,
    )

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="RESOURCE_USAGE_EVENT_CREATE",
        resource_type="resource_usage_events",
        resource_id=str(event.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={
            "api_key_id": event.api_key_id,
            "ai_account_id": event.ai_account_id,
            "department_id": event.department_id,
            "total_tokens": event.total_tokens,
            "estimated_cost_usd": str(event.estimated_cost_usd),
            "event_source": event.event_source,
        },
    )

    db.commit()
    db.refresh(event)
    return ResourceUsageEventRead.model_validate(event)
