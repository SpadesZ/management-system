# File Path: backend/app/api/routers/usage_purposes.py
# Timestamp: 2026-05-26T12:00:00+08:00
# Version: v0.1

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import asc, desc, func, select

from app.api.deps import CurrentUserDep, DBSessionDep, get_pagination_query, require_roles
from app.core.audit import write_audit_log
from app.models.entities import UsagePurpose, User
from app.models.enums import RoleCode
from app.schemas.common import PaginationMeta, PaginationQuery
from app.schemas.usage_purpose import UsagePurposeCreate, UsagePurposeRead

router = APIRouter(prefix="/usage-purposes", tags=["usage-purposes"])


@router.get("", response_model=dict)
def list_usage_purposes(
    db: DBSessionDep,
    _: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
) -> dict:
    stmt = select(UsagePurpose)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    if pagination.sort_by == "code":
        order_column = UsagePurpose.code
    elif pagination.sort_by == "name":
        order_column = UsagePurpose.name
    else:
        order_column = UsagePurpose.created_at

    ordering = asc(order_column) if pagination.sort_order == "asc" else desc(order_column)

    rows = db.scalars(
        stmt.order_by(ordering)
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    ).all()

    return {
        "items": [UsagePurposeRead.model_validate(row).model_dump(mode="json") for row in rows],
        "meta": PaginationMeta(page=pagination.page, page_size=pagination.page_size, total=int(total)).model_dump(),
    }


@router.post("", response_model=UsagePurposeRead)
def create_usage_purpose(
    payload: UsagePurposeCreate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.FINANCE.value)),
) -> UsagePurposeRead:
    normalized_code = payload.code.strip().upper()
    if not normalized_code:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="code 不可為空")

    normalized_status = payload.status.strip().upper()
    if normalized_status not in {"ACTIVE", "INACTIVE"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="status must be ACTIVE or INACTIVE")

    duplicated = db.scalar(select(UsagePurpose).where(func.lower(UsagePurpose.code) == normalized_code.lower()))
    if duplicated is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="usage purpose code already exists")

    entity = UsagePurpose(
        code=normalized_code,
        name=payload.name.strip(),
        description=payload.description,
        status=normalized_status,
        created_by_user_id=actor.id,
    )
    db.add(entity)
    db.flush()

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="USAGE_PURPOSE_CREATE",
        resource_type="usage_purposes",
        resource_id=str(entity.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={
            "code": entity.code,
            "name": entity.name,
            "status": entity.status,
        },
    )

    db.commit()
    db.refresh(entity)
    return UsagePurposeRead.model_validate(entity)
