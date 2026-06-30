# File Path: backend/app/api/routers/users.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import asc, desc, func, select

from app.api.deps import CurrentUserDep, DBSessionDep, get_pagination_query, require_roles
from app.core.audit import write_audit_log
from app.core.security import security_manager
from app.models.entities import Department, User
from app.models.enums import RoleCode
from app.schemas.common import PaginationMeta, PaginationQuery
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services.scope_filter import allowed_department_ids, apply_department_scope, get_scope_context

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=dict)
def list_users(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
) -> dict:
    context = get_scope_context(current_user)
    allowed_ids = allowed_department_ids(db, context)

    base_stmt = select(User)
    base_stmt = apply_department_scope(base_stmt, User.department_id, allowed_ids)

    total = db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0

    order_column = User.created_at if pagination.sort_by == "created_at" else User.id
    ordering = asc(order_column) if pagination.sort_order == "asc" else desc(order_column)

    rows = db.scalars(
        base_stmt.order_by(ordering)
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    ).all()

    return {
        "items": [UserRead.model_validate(row).model_dump() for row in rows],
        "meta": PaginationMeta(page=pagination.page, page_size=pagination.page_size, total=int(total)).model_dump(),
    }


@router.post("", response_model=UserRead)
def create_user(
    payload: UserCreate,
    db: DBSessionDep,
    _: User = Depends(require_roles(RoleCode.ADMIN.value)),
) -> UserRead:
    department = db.get(Department, payload.department_id)
    if department is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid department_id")

    if payload.manager_id is not None:
        manager = db.get(User, payload.manager_id)
        if manager is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid manager_id")

    existing = db.scalar(select(User).where((User.email == payload.email) | (User.employee_no == payload.employee_no)))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

    entity = User(
        employee_no=payload.employee_no,
        name=payload.name,
        email=payload.email,
        password_hash=security_manager.hash_password(payload.password),
        department_id=payload.department_id,
        manager_id=payload.manager_id,
        role=payload.role,
        status=payload.status,
    )
    db.add(entity)
    db.flush()

    write_audit_log(
        db,
        actor_user_id=_.id,
        action="USER_CREATE",
        resource_type="users",
        resource_id=str(entity.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={"email": entity.email, "role": entity.role, "department_id": entity.department_id},
    )

    db.commit()
    db.refresh(entity)
    return UserRead.model_validate(entity)


@router.patch("/{user_id}", response_model=UserRead)
def patch_user(
    user_id: int,
    payload: UserUpdate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value)),
) -> UserRead:
    entity = db.get(User, user_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    before = {
        "name": entity.name,
        "department_id": entity.department_id,
        "manager_id": entity.manager_id,
        "role": entity.role,
        "status": entity.status,
    }

    if payload.name is not None:
        entity.name = payload.name
    if payload.department_id is not None:
        department = db.get(Department, payload.department_id)
        if department is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid department_id")
        entity.department_id = payload.department_id
    if payload.manager_id is not None:
        manager = db.get(User, payload.manager_id)
        if manager is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid manager_id")
        entity.manager_id = payload.manager_id
    if payload.role is not None:
        entity.role = payload.role
    if payload.status is not None:
        entity.status = payload.status
    if payload.password is not None:
        entity.password_hash = security_manager.hash_password(payload.password)

    db.flush()

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="USER_UPDATE",
        resource_type="users",
        resource_id=str(entity.id),
        source="API",
        ip_address=None,
        before_json=before,
        after_json={
            "name": entity.name,
            "department_id": entity.department_id,
            "manager_id": entity.manager_id,
            "role": entity.role,
            "status": entity.status,
        },
    )

    db.commit()
    db.refresh(entity)
    return UserRead.model_validate(entity)
