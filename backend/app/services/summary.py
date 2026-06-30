# File Path: backend/app/services/summary.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from app.models.entities import UsageDailySummary, UsageEvent


def rebuild_daily_summary(db: Session, target_date: date) -> int:
    start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=UTC)
    end = start + timedelta(days=1)

    db.execute(delete(UsageDailySummary).where(UsageDailySummary.date == target_date))

    aggregation_stmt = (
        select(
            func.date(UsageEvent.created_at).label("date"),
            UsageEvent.user_id,
            UsageEvent.department_id,
            UsageEvent.project_id,
            UsageEvent.provider_id,
            UsageEvent.model_id,
            UsageEvent.api_key_id,
            func.count(UsageEvent.id).label("request_count"),
            func.coalesce(func.sum(UsageEvent.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(UsageEvent.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(UsageEvent.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(UsageEvent.estimated_cost_usd), 0).label("total_cost_usd"),
            func.coalesce(func.sum(case((UsageEvent.status != "SUCCESS", 1), else_=0)), 0).label("error_count"),
            func.coalesce(func.avg(UsageEvent.latency_ms), 0).label("avg_latency_ms"),
        )
        .where(UsageEvent.created_at >= start, UsageEvent.created_at < end)
        .group_by(
            func.date(UsageEvent.created_at),
            UsageEvent.user_id,
            UsageEvent.department_id,
            UsageEvent.project_id,
            UsageEvent.provider_id,
            UsageEvent.model_id,
            UsageEvent.api_key_id,
        )
    )

    rows = db.execute(aggregation_stmt).all()
    for row in rows:
        summary = UsageDailySummary(
            date=row.date,
            user_id=row.user_id,
            department_id=row.department_id,
            project_id=row.project_id,
            provider_id=row.provider_id,
            model_id=row.model_id,
            api_key_id=row.api_key_id,
            request_count=row.request_count,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            total_tokens=row.total_tokens,
            total_cost_usd=row.total_cost_usd,
            error_count=row.error_count,
            avg_latency_ms=row.avg_latency_ms,
        )
        db.add(summary)

    db.flush()
    return len(rows)
