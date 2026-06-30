# File Path: backend/app/services/export_service.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

import csv
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import CostLedger, ExportJob
from app.models.enums import JobStatus


def create_export_job(db: Session, requester_user_id: int, export_type: str, filters_json: dict) -> ExportJob:
    job = ExportJob(
        requester_user_id=requester_user_id,
        export_type=export_type,
        filters_json=filters_json,
        status=JobStatus.PENDING.value,
    )
    db.add(job)
    db.flush()
    return job


def process_export_job(db: Session, job: ExportJob) -> ExportJob:
    settings = get_settings()
    export_dir = Path(settings.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)

    job.status = JobStatus.RUNNING.value
    job.started_at = datetime.now(UTC)
    db.flush()

    try:
        output_file = export_dir / f"export_{job.id}_{int(datetime.now(UTC).timestamp())}.csv"
        stmt = select(CostLedger).order_by(CostLedger.created_at.desc()).limit(20000)
        records = db.scalars(stmt).all()

        with output_file.open("w", encoding="utf-8", newline="") as fp:
            writer = csv.writer(fp)
            writer.writerow(
                [
                    "request_id",
                    "user_id",
                    "department_id",
                    "project_id",
                    "provider_id",
                    "model_id",
                    "currency",
                    "input_tokens",
                    "output_tokens",
                    "estimated_cost",
                    "settled_cost",
                    "ledger_type",
                    "created_at",
                ]
            )
            for row in records:
                writer.writerow(
                    [
                        row.request_id,
                        row.user_id,
                        row.department_id,
                        row.project_id,
                        row.provider_id,
                        row.model_id,
                        row.currency,
                        row.input_tokens,
                        row.output_tokens,
                        str(row.estimated_cost),
                        str(row.settled_cost),
                        row.ledger_type,
                        row.created_at.isoformat(),
                    ]
                )

        job.file_path = str(output_file)
        job.file_size_bytes = os.path.getsize(output_file)
        job.expires_at = datetime.now(UTC) + timedelta(days=1)
        job.status = JobStatus.SUCCESS.value
        job.finished_at = datetime.now(UTC)
        db.flush()
        return job
    except Exception as exc:  # defensive fallback to keep job state consistent
        job.status = JobStatus.FAILED.value
        job.error_message = str(exc)
        job.finished_at = datetime.now(UTC)
        db.flush()
        return job
