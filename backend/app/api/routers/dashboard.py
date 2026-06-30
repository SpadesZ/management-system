# File Path: backend/app/api/routers/dashboard.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from datetime import UTC, date, datetime

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.deps import CurrentUserDep, DBSessionDep
from app.models.entities import Alert, UsageDailySummary
from app.schemas.cost import AlertRead, DashboardSummaryResponse
from app.services.scope_filter import allowed_department_ids, get_scope_context

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(db: DBSessionDep, current_user: CurrentUserDep) -> DashboardSummaryResponse:
    context = get_scope_context(current_user)
    allowed_ids = allowed_department_ids(db, context)

    today = date.today()
    month_start = date(today.year, today.month, 1)

    today_stmt = select(
        func.coalesce(func.sum(UsageDailySummary.total_tokens), 0),
        func.coalesce(func.sum(UsageDailySummary.total_cost_usd), 0),
    ).where(UsageDailySummary.date == today)

    month_stmt = select(
        func.coalesce(func.sum(UsageDailySummary.total_tokens), 0),
        func.coalesce(func.sum(UsageDailySummary.total_cost_usd), 0),
    ).where(UsageDailySummary.date >= month_start, UsageDailySummary.date <= today)

    if allowed_ids is not None:
        today_stmt = today_stmt.where(UsageDailySummary.department_id.in_(allowed_ids))
        month_stmt = month_stmt.where(UsageDailySummary.department_id.in_(allowed_ids))

    today_row = db.execute(today_stmt).one()
    month_row = db.execute(month_stmt).one()

    return DashboardSummaryResponse(
        today_tokens=int(today_row[0] or 0),
        today_cost_usd=today_row[1] or 0,
        month_tokens=int(month_row[0] or 0),
        month_cost_usd=month_row[1] or 0,
    )


@router.get("/alerts", response_model=list[AlertRead])
def dashboard_alerts(db: DBSessionDep, _: CurrentUserDep) -> list[AlertRead]:
    rows = db.scalars(
        select(Alert)
        .where(Alert.status.in_(["OPEN", "ACKNOWLEDGED"]))
        .order_by(Alert.triggered_at.desc())
        .limit(50)
    ).all()
    return [AlertRead.model_validate(row) for row in rows]
