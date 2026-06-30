# File Path: backend/app/api/routers/projects.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import asc, desc, func, select

from app.api.deps import CurrentUserDep, DBSessionDep, get_pagination_query, require_roles
from app.core.audit import write_audit_log
from app.models.entities import Project, User
from app.models.enums import RoleCode
from app.schemas.common import PaginationMeta, PaginationQuery
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services.scope_filter import allowed_department_ids, get_scope_context

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=dict)
def list_projects(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
) -> dict:
    context = get_scope_context(current_user)
    allowed_ids = allowed_department_ids(db, context)

    stmt = select(Project)
    if allowed_ids is not None:
        stmt = stmt.where(Project.department_id.in_(allowed_ids))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    order_column = Project.created_at if pagination.sort_by == "created_at" else Project.id
    ordering = asc(order_column) if pagination.sort_order == "asc" else desc(order_column)

    rows = db.scalars(
        stmt.order_by(ordering)
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    ).all()

    return {
        "items": [ProjectRead.model_validate(row).model_dump() for row in rows],
        "meta": PaginationMeta(page=pagination.page, page_size=pagination.page_size, total=int(total)).model_dump(),
    }


@router.post("", response_model=ProjectRead)
def create_project(
    payload: ProjectCreate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.MANAGER.value)),
) -> ProjectRead:
    existing = db.scalar(select(Project).where(Project.code == payload.code))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project code already exists")

    entity = Project(
        code=payload.code,
        name=payload.name,
        department_id=payload.department_id,
        owner_user_id=payload.owner_user_id,
        status=payload.status,
    )
    db.add(entity)
    db.flush()

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="PROJECT_CREATE",
        resource_type="projects",
        resource_id=str(entity.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={"code": entity.code, "department_id": entity.department_id},
    )

    db.commit()
    db.refresh(entity)
    return ProjectRead.model_validate(entity)


@router.patch("/{project_id}", response_model=ProjectRead)
def patch_project(
    project_id: int,
    payload: ProjectUpdate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.MANAGER.value)),
) -> ProjectRead:
    entity = db.get(Project, project_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if payload.name is not None:
        entity.name = payload.name
    if payload.department_id is not None:
        entity.department_id = payload.department_id
    if payload.owner_user_id is not None:
        entity.owner_user_id = payload.owner_user_id
    if payload.status is not None:
        entity.status = payload.status

    db.flush()

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="PROJECT_UPDATE",
        resource_type="projects",
        resource_id=str(entity.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={
            "name": entity.name,
            "department_id": entity.department_id,
            "owner_user_id": entity.owner_user_id,
            "status": entity.status,
        },
    )

    db.commit()
    db.refresh(entity)
    return ProjectRead.model_validate(entity)
