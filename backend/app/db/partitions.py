# File Path: backend/app/db/partitions.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from datetime import UTC, datetime

from dateutil.relativedelta import relativedelta
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _month_start(dt: datetime) -> datetime:
    return datetime(dt.year, dt.month, 1, tzinfo=UTC)


def ensure_usage_event_partitions(engine: Engine, future_months: int = 3) -> None:
    now = _month_start(datetime.now(UTC))
    months = [now + relativedelta(months=offset) for offset in range(0, future_months + 1)]

    with engine.begin() as conn:
        for month_start in months:
            next_month = month_start + relativedelta(months=1)
            partition_name = f"usage_events_{month_start.year}_{month_start.month:02d}"
            sql = text(
                f"""
                CREATE TABLE IF NOT EXISTS {partition_name}
                PARTITION OF usage_events
                FOR VALUES FROM (:from_ts) TO (:to_ts)
                """
            )
            conn.execute(sql, {"from_ts": month_start, "to_ts": next_month})


def drop_expired_usage_partitions(engine: Engine, retention_months: int = 12) -> None:
    boundary_month = _month_start(datetime.now(UTC)) - relativedelta(months=retention_months)
    with engine.begin() as conn:
        query = text(
            """
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public' AND tablename LIKE 'usage_events_%'
            """
        )
        rows = conn.execute(query).fetchall()
        for row in rows:
            table_name = row[0]
            try:
                suffix = table_name.replace("usage_events_", "")
                year, month = suffix.split("_")
                table_month = datetime(int(year), int(month), 1, tzinfo=UTC)
                if table_month < boundary_month:
                    conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
            except ValueError:
                continue
