# File Path: backend/app/api/routers/models.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import asc, desc, func, select

from app.api.deps import CurrentUserDep, DBSessionDep, get_pagination_query, require_roles
from app.core.audit import write_audit_log
from app.models.entities import Model, ModelPrice, User
from app.models.enums import RoleCode
from app.schemas.common import PaginationMeta, PaginationQuery
from app.schemas.provider_model import (
    ModelCreate,
    ModelPriceCreate,
    ModelPriceRead,
    ModelRead,
    ModelUpdate,
)
from app.services.pricing import validate_model_price_no_overlap

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=dict)
def list_models(
    db: DBSessionDep,
    _: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
) -> dict:
    stmt = select(Model)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    order_column = Model.created_at if pagination.sort_by == "created_at" else Model.id
    ordering = asc(order_column) if pagination.sort_order == "asc" else desc(order_column)
    rows = db.scalars(
        stmt.order_by(ordering)
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    ).all()

    return {
        "items": [ModelRead.model_validate(row).model_dump() for row in rows],
        "meta": PaginationMeta(page=pagination.page, page_size=pagination.page_size, total=int(total)).model_dump(),
    }


@router.post("", response_model=ModelRead)
def create_model(
    payload: ModelCreate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value)),
) -> ModelRead:
    entity = Model(
        provider_id=payload.provider_id,
        model_code=payload.model_code,
        display_name=payload.display_name,
        context_window=payload.context_window,
        capabilities_json=payload.capabilities_json,
        status=payload.status,
    )
    db.add(entity)
    db.flush()

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="MODEL_CREATE",
        resource_type="models",
        resource_id=str(entity.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={"provider_id": entity.provider_id, "model_code": entity.model_code},
    )

    db.commit()
    db.refresh(entity)
    return ModelRead.model_validate(entity)


@router.patch("/{model_id}", response_model=ModelRead)
def patch_model(
    model_id: int,
    payload: ModelUpdate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value)),
) -> ModelRead:
    entity = db.get(Model, model_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")

    if payload.display_name is not None:
        entity.display_name = payload.display_name
    if payload.context_window is not None:
        entity.context_window = payload.context_window
    if payload.capabilities_json is not None:
        entity.capabilities_json = payload.capabilities_json
    if payload.status is not None:
        entity.status = payload.status

    db.flush()
    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="MODEL_UPDATE",
        resource_type="models",
        resource_id=str(entity.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={
            "display_name": entity.display_name,
            "context_window": entity.context_window,
            "status": entity.status,
        },
    )

    db.commit()
    db.refresh(entity)
    return ModelRead.model_validate(entity)


@router.post("/{model_id}/prices", response_model=ModelPriceRead)
def create_model_price(
    model_id: int,
    payload: ModelPriceCreate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.FINANCE.value)),
) -> ModelPriceRead:
    if model_id != payload.model_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="model_id mismatch")

    is_valid = validate_model_price_no_overlap(
        db,
        model_id=payload.model_id,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
    )
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="model price period overlaps")

    price = ModelPrice(
        model_id=payload.model_id,
        input_price_per_1m=payload.input_price_per_1m,
        output_price_per_1m=payload.output_price_per_1m,
        currency=payload.currency,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
    )
    db.add(price)
    db.flush()

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="MODEL_PRICE_CREATE",
        resource_type="model_prices",
        resource_id=str(price.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={
            "model_id": price.model_id,
            "input_price_per_1m": str(price.input_price_per_1m),
            "output_price_per_1m": str(price.output_price_per_1m),
            "effective_from": price.effective_from.isoformat(),
            "effective_to": price.effective_to.isoformat() if price.effective_to else None,
        },
    )

    db.commit()
    db.refresh(price)
    return ModelPriceRead.model_validate(price)
