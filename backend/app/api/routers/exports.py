# File Path: backend/app/api/routers/exports.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DBSessionDep, require_roles
from app.core.audit import write_audit_log
from app.models.entities import ExportJob, User
from app.models.enums import RoleCode
from app.schemas.export_job import ExportCreateRequest, ExportJobRead
from app.services.export_service import create_export_job

router = APIRouter(tags=["exports"])


@router.post("/exports", response_model=ExportJobRead)
def create_export(
    payload: ExportCreateRequest,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.FINANCE.value, RoleCode.MANAGER.value)),
) -> ExportJobRead:
    job = create_export_job(db, requester_user_id=actor.id, export_type=payload.export_type, filters_json=payload.filters_json)

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="EXPORT_CREATE",
        resource_type="export_jobs",
        resource_id=str(job.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={"export_type": job.export_type, "status": job.status},
    )

    db.commit()
    db.refresh(job)
    return ExportJobRead.model_validate(job)


@router.get("/exports", response_model=list[ExportJobRead])
def list_exports(
    db: DBSessionDep,
    actor: CurrentUserDep,
) -> list[ExportJobRead]:
    stmt = select(ExportJob).order_by(ExportJob.created_at.desc()).limit(200)
    if actor.role not in {RoleCode.ADMIN.value, RoleCode.FINANCE.value}:
        stmt = stmt.where(ExportJob.requester_user_id == actor.id)
    rows = db.scalars(stmt).all()
    return [ExportJobRead.model_validate(row) for row in rows]
