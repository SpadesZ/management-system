# File Path: backend/app/api/routers/analytics.py
# Timestamp: 2026-05-26T12:00:00+08:00
# Version: v0.1

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select

from app.api.deps import CurrentUserDep, DBSessionDep, get_pagination_query
from app.schemas.common import PaginationMeta, PaginationQuery
from app.models.entities import WorkOutput
from app.services.scope_filter import allowed_department_ids, apply_department_scope, get_scope_context

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _month_range() -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    return datetime(now.year, now.month, 1, tzinfo=UTC), now


def _to_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _to_text(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.000001")))


def _roi_ratio(value: Decimal, cost: Decimal) -> str | None:
    if cost <= 0:
        return None
    return _to_text(value / cost)


@router.get("/roi", response_model=dict)
def get_roi_analytics(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
    group_by: str = Query(default="department", pattern="^(department|user|project|asset)$"),
) -> dict:
    context = get_scope_context(current_user)
    allowed_ids = allowed_department_ids(db, context)

    default_start, default_end = _month_range()
    start_at = pagination.start_at or default_start
    end_at = pagination.end_at or default_end

    base_filter_stmt = select(WorkOutput).where(
        WorkOutput.status == "APPROVED",
        WorkOutput.created_at >= start_at,
        WorkOutput.created_at <= end_at,
    )
    base_filter_stmt = apply_department_scope(base_filter_stmt, WorkOutput.department_id, allowed_ids)

    base_subquery = base_filter_stmt.subquery()

    totals_row = db.execute(
        select(
            func.coalesce(func.sum(base_subquery.c.cost_usd), 0),
            func.coalesce(func.sum(base_subquery.c.value_usd), 0),
            func.count(base_subquery.c.id),
        )
    ).one()

    total_cost = _to_decimal(totals_row[0])
    total_value = _to_decimal(totals_row[1])
    total_count = int(totals_row[2] or 0)

    if group_by == "asset":
        grouped_stmt = (
            select(
                base_subquery.c.api_key_id,
                base_subquery.c.ai_account_id,
                func.coalesce(func.sum(base_subquery.c.cost_usd), 0).label("cost_usd"),
                func.coalesce(func.sum(base_subquery.c.value_usd), 0).label("value_usd"),
                func.count(base_subquery.c.id).label("output_count"),
            )
            .group_by(base_subquery.c.api_key_id, base_subquery.c.ai_account_id)
            .order_by(desc(func.coalesce(func.sum(base_subquery.c.value_usd), 0)))
        )
    else:
        column_map = {
            "department": base_subquery.c.department_id,
            "user": base_subquery.c.user_id,
            "project": base_subquery.c.project_id,
        }
        grouped_col = column_map[group_by]

        grouped_stmt = (
            select(
                grouped_col.label("group_id"),
                func.coalesce(func.sum(base_subquery.c.cost_usd), 0).label("cost_usd"),
                func.coalesce(func.sum(base_subquery.c.value_usd), 0).label("value_usd"),
                func.count(base_subquery.c.id).label("output_count"),
            )
            .group_by(grouped_col)
            .order_by(desc(func.coalesce(func.sum(base_subquery.c.value_usd), 0)))
        )

    total_groups = db.scalar(select(func.count()).select_from(grouped_stmt.subquery())) or 0

    rows = db.execute(
        grouped_stmt
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    ).all()

    items: list[dict] = []
    if group_by == "asset":
        for row in rows:
            api_key_id = int(row[0]) if row[0] is not None else None
            ai_account_id = int(row[1]) if row[1] is not None else None
            cost_usd = _to_decimal(row[2])
            value_usd = _to_decimal(row[3])
            output_count = int(row[4] or 0)

            if api_key_id is not None:
                group_key = f"API_KEY:{api_key_id}"
                asset_type = "API_KEY"
                asset_id = api_key_id
            else:
                group_key = f"AI_ACCOUNT:{ai_account_id}"
                asset_type = "AI_ACCOUNT"
                asset_id = ai_account_id

            items.append(
                {
                    "group_key": group_key,
                    "asset_type": asset_type,
                    "asset_id": asset_id,
                    "cost_usd": _to_text(cost_usd),
                    "value_usd": _to_text(value_usd),
                    "output_count": output_count,
                    "roi_ratio": _roi_ratio(value_usd, cost_usd),
                }
            )
    else:
        for row in rows:
            group_id = int(row[0]) if row[0] is not None else None
            cost_usd = _to_decimal(row[1])
            value_usd = _to_decimal(row[2])
            output_count = int(row[3] or 0)
            items.append(
                {
                    "group_key": f"{group_by.upper()}:{group_id}" if group_id is not None else f"{group_by.upper()}:NULL",
                    "group_id": group_id,
                    "cost_usd": _to_text(cost_usd),
                    "value_usd": _to_text(value_usd),
                    "output_count": output_count,
                    "roi_ratio": _roi_ratio(value_usd, cost_usd),
                }
            )

    return {
        "group_by": group_by,
        "range_start": start_at.isoformat(),
        "range_end": end_at.isoformat(),
        "totals": {
            "cost_usd": _to_text(total_cost),
            "value_usd": _to_text(total_value),
            "output_count": total_count,
            "roi_ratio": _roi_ratio(total_value, total_cost),
        },
        "items": items,
        "meta": PaginationMeta(page=pagination.page, page_size=pagination.page_size, total=int(total_groups)).model_dump(),
    }
