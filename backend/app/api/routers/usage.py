# File Path: backend/app/api/routers/usage.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from datetime import UTC, datetime

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends
from sqlalchemy import asc, desc, func, select

from app.api.deps import CurrentUserDep, DBSessionDep, get_pagination_query
from app.models.entities import UsageEvent
from app.schemas.common import PaginationMeta, PaginationQuery
from app.services.scope_filter import allowed_department_ids, apply_department_scope, get_scope_context

router = APIRouter(tags=["usage"])


@router.get("/usage-events", response_model=dict)
def list_usage_events(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
) -> dict:
    context = get_scope_context(current_user)
    allowed_ids = allowed_department_ids(db, context)

    start_at = pagination.start_at or datetime(datetime.now(UTC).year, datetime.now(UTC).month, 1, tzinfo=UTC)
    end_at = pagination.end_at or (start_at + relativedelta(months=1))

    stmt = select(UsageEvent).where(UsageEvent.created_at >= start_at, UsageEvent.created_at < end_at)
    stmt = apply_department_scope(stmt, UsageEvent.department_id, allowed_ids)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    order_column = UsageEvent.created_at if pagination.sort_by == "created_at" else UsageEvent.id
    ordering = asc(order_column) if pagination.sort_order == "asc" else desc(order_column)

    rows = db.scalars(
        stmt.order_by(ordering)
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    ).all()

    items = [
        {
            "id": row.id,
            "request_id": row.request_id,
            "created_at": row.created_at,
            "user_id": row.user_id,
            "department_id": row.department_id,
            "project_id": row.project_id,
            "provider_id": row.provider_id,
            "model_id": row.model_id,
            "api_key_id": row.api_key_id,
            "price_version_id": row.price_version_id,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "total_tokens": row.total_tokens,
            "estimated_cost_usd": row.estimated_cost_usd,
            "latency_ms": row.latency_ms,
            "status": row.status,
            "error_code": row.error_code,
        }
        for row in rows
    ]

    return {
        "items": items,
        "meta": PaginationMeta(page=pagination.page, page_size=pagination.page_size, total=int(total)).model_dump(),
    }
