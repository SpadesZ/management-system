# File Path: backend/app/worker.py
# Timestamp: 2026-05-26T12:00:00+08:00
# Version: v0.2

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.session import SessionLocal
from app.db.init_db import init_db
from app.models.entities import AggregationJob, ExportJob
from app.models.enums import JobStatus
from app.services.assistant import cleanup_expired_assistant_messages
from app.services.export_service import process_export_job
from app.services.resource_limits import rebuild_resource_limit_states
from app.services.summary import rebuild_daily_summary


_last_limit_rebuild_at: datetime | None = None
_last_assistant_retention_cleanup_at: datetime | None = None


def run_worker_tick() -> None:
    global _last_assistant_retention_cleanup_at, _last_limit_rebuild_at

    db = SessionLocal()
    try:
        pending_exports = db.scalars(select(ExportJob).where(ExportJob.status == JobStatus.PENDING.value)).all()
        for job in pending_exports:
            process_export_job(db, job)

        pending_agg_jobs = db.scalars(
            select(AggregationJob).where(AggregationJob.status == JobStatus.PENDING.value).order_by(AggregationJob.created_at)
        ).all()
        for job in pending_agg_jobs:
            job.status = JobStatus.RUNNING.value
            job.started_at = datetime.now(UTC)
            db.flush()
            try:
                target_date = (job.period_start - timedelta(hours=0)).date()
                processed_rows = rebuild_daily_summary(db, target_date)
                job.processed_rows = processed_rows
                job.status = JobStatus.SUCCESS.value
            except Exception as exc:  # defensive fallback for background loop
                job.status = JobStatus.FAILED.value
                job.error_message = str(exc)
            finally:
                job.finished_at = datetime.now(UTC)
            db.flush()

        now = datetime.now(UTC)
        if _last_limit_rebuild_at is None or (now - _last_limit_rebuild_at) >= timedelta(minutes=5):
            rebuild_resource_limit_states(db, now=now)
            _last_limit_rebuild_at = now

        if _last_assistant_retention_cleanup_at is None or (now - _last_assistant_retention_cleanup_at) >= timedelta(hours=1):
            cleanup_expired_assistant_messages(db, now=now, retention_days=180)
            _last_assistant_retention_cleanup_at = now

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    import time

    init_db()

    while True:
        run_worker_tick()
        time.sleep(5)


if __name__ == "__main__":
    main()
