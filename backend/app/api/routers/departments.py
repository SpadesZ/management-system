# File Path: backend/app/api/routers/departments.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import asc, desc, func, select

from app.api.deps import CurrentUserDep, DBSessionDep, get_pagination_query, require_roles
from app.core.audit import write_audit_log
from app.models.entities import Department, User
from app.models.enums import RoleCode
from app.schemas.common import PaginationMeta, PaginationQuery
from app.schemas.department import DepartmentCreate, DepartmentRead, DepartmentUpdate
from app.services.scope_filter import allowed_department_ids, get_scope_context

router = APIRouter(prefix="/departments", tags=["departments"])


@router.get("", response_model=dict)
def list_departments(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
) -> dict:
    context = get_scope_context(current_user)
    allowed_ids = allowed_department_ids(db, context)

    stmt = select(Department)
    if allowed_ids is not None:
        stmt = stmt.where(Department.id.in_(allowed_ids))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order_column = Department.created_at if pagination.sort_by == "created_at" else Department.id
    ordering = asc(order_column) if pagination.sort_order == "asc" else desc(order_column)

    rows = db.scalars(
        stmt.order_by(ordering)
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    ).all()

    return {
        "items": [DepartmentRead.model_validate(row).model_dump() for row in rows],
        "meta": PaginationMeta(page=pagination.page, page_size=pagination.page_size, total=int(total)).model_dump(),
    }


@router.post("", response_model=DepartmentRead)
def create_department(
    payload: DepartmentCreate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value)),
) -> DepartmentRead:
    entity = Department(
        parent_id=payload.parent_id,
        name=payload.name,
        cost_center_code=payload.cost_center_code,
        manager_user_id=payload.manager_user_id,
        monthly_budget_usd=payload.monthly_budget_usd,
        status=payload.status,
    )
    db.add(entity)
    db.flush()

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="DEPARTMENT_CREATE",
        resource_type="departments",
        resource_id=str(entity.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={"name": entity.name, "parent_id": entity.parent_id},
    )

    db.commit()
    db.refresh(entity)
    return DepartmentRead.model_validate(entity)


@router.patch("/{department_id}", response_model=DepartmentRead)
def patch_department(
    department_id: int,
    payload: DepartmentUpdate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.MANAGER.value)),
) -> DepartmentRead:
    entity = db.get(Department, department_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

    if payload.parent_id is not None:
        entity.parent_id = payload.parent_id
    if payload.name is not None:
        entity.name = payload.name
    if payload.cost_center_code is not None:
        entity.cost_center_code = payload.cost_center_code
    if payload.manager_user_id is not None:
        entity.manager_user_id = payload.manager_user_id
    if payload.monthly_budget_usd is not None:
        entity.monthly_budget_usd = payload.monthly_budget_usd
    if payload.status is not None:
        entity.status = payload.status

    db.flush()

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="DEPARTMENT_UPDATE",
        resource_type="departments",
        resource_id=str(entity.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={
            "name": entity.name,
            "parent_id": entity.parent_id,
            "monthly_budget_usd": str(entity.monthly_budget_usd),
            "status": entity.status,
        },
    )

    db.commit()
    db.refresh(entity)
    return DepartmentRead.model_validate(entity)
