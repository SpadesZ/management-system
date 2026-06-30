# File Path: backend/app/services/resource_limits.py
# Timestamp: 2026-05-26T12:00:00+08:00
# Version: v0.1

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import ResourceLimitState, ResourceUsageEvent, UsageEvent


def _normalize_now(now: datetime | None = None) -> datetime:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        return current.replace(tzinfo=UTC)
    return current.astimezone(UTC)


def _sum_usage_tokens(
    db: Session,
    *,
    api_key_id: int,
    start_at: datetime,
    end_at: datetime,
) -> int:
    value = db.scalar(
        select(func.coalesce(func.sum(UsageEvent.total_tokens), 0)).where(
            UsageEvent.api_key_id == api_key_id,
            UsageEvent.created_at >= start_at,
            UsageEvent.created_at <= end_at,
        )
    )
    return int(value or 0)


def _sum_resource_usage_tokens(
    db: Session,
    *,
    api_key_id: int | None,
    ai_account_id: int | None,
    start_at: datetime,
    end_at: datetime,
) -> int:
    stmt = select(func.coalesce(func.sum(ResourceUsageEvent.total_tokens), 0)).where(
        ResourceUsageEvent.occurred_at >= start_at,
        ResourceUsageEvent.occurred_at <= end_at,
    )

    if api_key_id is not None:
        stmt = stmt.where(ResourceUsageEvent.api_key_id == api_key_id)
    if ai_account_id is not None:
        stmt = stmt.where(ResourceUsageEvent.ai_account_id == ai_account_id)

    value = db.scalar(stmt)
    return int(value or 0)


def calculate_utilization_pct(
    *,
    tokens_5h: int,
    tokens_today: int,
    tokens_week: int,
    tokens_month: int,
    limit_5h: int | None,
    limit_day: int | None,
    limit_week: int | None,
    limit_month: int | None,
) -> Decimal:
    ratios: list[Decimal] = []

    if limit_5h and limit_5h > 0:
        ratios.append(Decimal(tokens_5h) / Decimal(limit_5h))
    if limit_day and limit_day > 0:
        ratios.append(Decimal(tokens_today) / Decimal(limit_day))
    if limit_week and limit_week > 0:
        ratios.append(Decimal(tokens_week) / Decimal(limit_week))
    if limit_month and limit_month > 0:
        ratios.append(Decimal(tokens_month) / Decimal(limit_month))

    if not ratios:
        return Decimal("0")

    return (max(ratios) * Decimal("100")).quantize(Decimal("0.0001"))


def recompute_limit_state(
    db: Session,
    *,
    api_key_id: int | None = None,
    ai_account_id: int | None = None,
    updated_by_user_id: int | None = None,
    now: datetime | None = None,
) -> ResourceLimitState:
    if (api_key_id is None) == (ai_account_id is None):
        raise ValueError("api_key_id 與 ai_account_id 必須擇一")

    current = _normalize_now(now)
    day_start = datetime(current.year, current.month, current.day, tzinfo=UTC)
    week_start = day_start - timedelta(days=day_start.weekday())
    month_start = datetime(current.year, current.month, 1, tzinfo=UTC)
    window_5h_start = current - timedelta(hours=5)

    stmt = select(ResourceLimitState)
    if api_key_id is not None:
        stmt = stmt.where(ResourceLimitState.api_key_id == api_key_id)
    else:
        stmt = stmt.where(ResourceLimitState.ai_account_id == ai_account_id)

    state = db.scalar(stmt)
    if state is None:
        state = ResourceLimitState(api_key_id=api_key_id, ai_account_id=ai_account_id)
        db.add(state)
        db.flush()

    if api_key_id is not None:
        tokens_5h = _sum_usage_tokens(db, api_key_id=api_key_id, start_at=window_5h_start, end_at=current)
        tokens_today = _sum_usage_tokens(db, api_key_id=api_key_id, start_at=day_start, end_at=current)
        tokens_week = _sum_usage_tokens(db, api_key_id=api_key_id, start_at=week_start, end_at=current)
        tokens_month = _sum_usage_tokens(db, api_key_id=api_key_id, start_at=month_start, end_at=current)

        tokens_5h += _sum_resource_usage_tokens(
            db,
            api_key_id=api_key_id,
            ai_account_id=None,
            start_at=window_5h_start,
            end_at=current,
        )
        tokens_today += _sum_resource_usage_tokens(
            db,
            api_key_id=api_key_id,
            ai_account_id=None,
            start_at=day_start,
            end_at=current,
        )
        tokens_week += _sum_resource_usage_tokens(
            db,
            api_key_id=api_key_id,
            ai_account_id=None,
            start_at=week_start,
            end_at=current,
        )
        tokens_month += _sum_resource_usage_tokens(
            db,
            api_key_id=api_key_id,
            ai_account_id=None,
            start_at=month_start,
            end_at=current,
        )
    else:
        tokens_5h = _sum_resource_usage_tokens(
            db,
            api_key_id=None,
            ai_account_id=ai_account_id,
            start_at=window_5h_start,
            end_at=current,
        )
        tokens_today = _sum_resource_usage_tokens(
            db,
            api_key_id=None,
            ai_account_id=ai_account_id,
            start_at=day_start,
            end_at=current,
        )
        tokens_week = _sum_resource_usage_tokens(
            db,
            api_key_id=None,
            ai_account_id=ai_account_id,
            start_at=week_start,
            end_at=current,
        )
        tokens_month = _sum_resource_usage_tokens(
            db,
            api_key_id=None,
            ai_account_id=ai_account_id,
            start_at=month_start,
            end_at=current,
        )

    state.tokens_5h = tokens_5h
    state.tokens_today = tokens_today
    state.tokens_week = tokens_week
    state.tokens_month = tokens_month
    state.window_5h_started_at = window_5h_start
    state.updated_by_user_id = updated_by_user_id
    state.utilization_pct = calculate_utilization_pct(
        tokens_5h=state.tokens_5h,
        tokens_today=state.tokens_today,
        tokens_week=state.tokens_week,
        tokens_month=state.tokens_month,
        limit_5h=state.limit_5h,
        limit_day=state.limit_day,
        limit_week=state.limit_week,
        limit_month=state.limit_month,
    )

    db.flush()
    return state


def rebuild_resource_limit_states(db: Session, now: datetime | None = None) -> int:
    current = _normalize_now(now)
    month_start = datetime(current.year, current.month, 1, tzinfo=UTC)

    api_key_ids = {
        int(row)
        for row in db.scalars(select(ResourceLimitState.api_key_id).where(ResourceLimitState.api_key_id.is_not(None))).all()
    }
    api_key_ids.update(
        int(row)
        for row in db.scalars(select(UsageEvent.api_key_id).where(UsageEvent.created_at >= month_start)).all()
        if row is not None
    )
    api_key_ids.update(
        int(row)
        for row in db.scalars(
            select(ResourceUsageEvent.api_key_id).where(
                ResourceUsageEvent.api_key_id.is_not(None),
                ResourceUsageEvent.occurred_at >= month_start,
            )
        ).all()
    )

    ai_account_ids = {
        int(row)
        for row in db.scalars(select(ResourceLimitState.ai_account_id).where(ResourceLimitState.ai_account_id.is_not(None))).all()
    }
    ai_account_ids.update(
        int(row)
        for row in db.scalars(
            select(ResourceUsageEvent.ai_account_id).where(
                ResourceUsageEvent.ai_account_id.is_not(None),
                ResourceUsageEvent.occurred_at >= month_start,
            )
        ).all()
    )

    processed = 0
    for api_key_id in sorted(api_key_ids):
        recompute_limit_state(db, api_key_id=api_key_id, now=current)
        processed += 1

    for ai_account_id in sorted(ai_account_ids):
        recompute_limit_state(db, ai_account_id=ai_account_id, now=current)
        processed += 1

    return processed
