# File Path: backend/app/api/routers/costs.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from datetime import UTC, datetime

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.deps import CurrentUserDep, DBSessionDep, get_pagination_query
from app.models.entities import CostLedger
from app.schemas.common import PaginationQuery
from app.services.scope_filter import allowed_department_ids, get_scope_context

router = APIRouter(prefix="/costs", tags=["costs"])


def _time_range(pagination: PaginationQuery) -> tuple[datetime, datetime]:
    start = pagination.start_at or datetime(datetime.now(UTC).year, datetime.now(UTC).month, 1, tzinfo=UTC)
    end = pagination.end_at or (start + relativedelta(months=1))
    return start, end


@router.get("/summary", response_model=dict)
def cost_summary(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
) -> dict:
    context = get_scope_context(current_user)
    allowed_ids = allowed_department_ids(db, context)
    start_at, end_at = _time_range(pagination)

    stmt = select(
        func.count(CostLedger.id),
        func.coalesce(func.sum(CostLedger.input_tokens + CostLedger.output_tokens), 0),
        func.coalesce(func.sum(CostLedger.settled_cost), 0),
    ).where(CostLedger.created_at >= start_at, CostLedger.created_at < end_at)

    if allowed_ids is not None:
        stmt = stmt.where(CostLedger.department_id.in_(allowed_ids))

    row = db.execute(stmt).one()
    return {
        "request_count": int(row[0] or 0),
        "total_tokens": int(row[1] or 0),
        "total_cost_usd": row[2] or 0,
    }


@router.get("/by-user", response_model=dict)
def cost_by_user(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
) -> dict:
    context = get_scope_context(current_user)
    allowed_ids = allowed_department_ids(db, context)
    start_at, end_at = _time_range(pagination)

    stmt = (
        select(
            CostLedger.user_id,
            func.count(CostLedger.id),
            func.coalesce(func.sum(CostLedger.input_tokens + CostLedger.output_tokens), 0),
            func.coalesce(func.sum(CostLedger.settled_cost), 0),
        )
        .where(CostLedger.created_at >= start_at, CostLedger.created_at < end_at)
        .group_by(CostLedger.user_id)
        .order_by(func.sum(CostLedger.settled_cost).desc())
        .limit(200)
    )
    if allowed_ids is not None:
        stmt = stmt.where(CostLedger.department_id.in_(allowed_ids))

    rows = db.execute(stmt).all()
    return {
        "items": [
            {
                "user_id": row[0],
                "request_count": int(row[1] or 0),
                "total_tokens": int(row[2] or 0),
                "total_cost_usd": row[3] or 0,
            }
            for row in rows
        ]
    }


@router.get("/by-department", response_model=dict)
def cost_by_department(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
) -> dict:
    context = get_scope_context(current_user)
    allowed_ids = allowed_department_ids(db, context)
    start_at, end_at = _time_range(pagination)

    stmt = (
        select(
            CostLedger.department_id,
            func.count(CostLedger.id),
            func.coalesce(func.sum(CostLedger.input_tokens + CostLedger.output_tokens), 0),
            func.coalesce(func.sum(CostLedger.settled_cost), 0),
        )
        .where(CostLedger.created_at >= start_at, CostLedger.created_at < end_at)
        .group_by(CostLedger.department_id)
        .order_by(func.sum(CostLedger.settled_cost).desc())
        .limit(200)
    )
    if allowed_ids is not None:
        stmt = stmt.where(CostLedger.department_id.in_(allowed_ids))

    rows = db.execute(stmt).all()
    return {
        "items": [
            {
                "department_id": row[0],
                "request_count": int(row[1] or 0),
                "total_tokens": int(row[2] or 0),
                "total_cost_usd": row[3] or 0,
            }
            for row in rows
        ]
    }


@router.get("/by-model", response_model=dict)
def cost_by_model(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
) -> dict:
    context = get_scope_context(current_user)
    allowed_ids = allowed_department_ids(db, context)
    start_at, end_at = _time_range(pagination)

    stmt = (
        select(
            CostLedger.model_id,
            func.count(CostLedger.id),
            func.coalesce(func.sum(CostLedger.input_tokens + CostLedger.output_tokens), 0),
            func.coalesce(func.sum(CostLedger.settled_cost), 0),
        )
        .where(CostLedger.created_at >= start_at, CostLedger.created_at < end_at)
        .group_by(CostLedger.model_id)
        .order_by(func.sum(CostLedger.settled_cost).desc())
        .limit(200)
    )
    if allowed_ids is not None:
        stmt = stmt.where(CostLedger.department_id.in_(allowed_ids))

    rows = db.execute(stmt).all()
    return {
        "items": [
            {
                "model_id": row[0],
                "request_count": int(row[1] or 0),
                "total_tokens": int(row[2] or 0),
                "total_cost_usd": row[3] or 0,
            }
            for row in rows
        ]
    }
