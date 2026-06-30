# File Path: backend/app/api/routers/asset_contracts.py
# Timestamp: 2026-05-26T12:00:00+08:00
# Version: v0.1

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import asc, desc, func, or_, select

from app.api.deps import CurrentUserDep, DBSessionDep, get_pagination_query, require_roles
from app.core.audit import write_audit_log
from app.models.entities import AIAccount, ApiKey, AssetContract, User
from app.models.enums import RoleCode
from app.schemas.asset_contract import AssetContractCreate, AssetContractRead, AssetContractUpdate
from app.schemas.common import PaginationMeta, PaginationQuery
from app.services.scope_filter import allowed_department_ids, get_scope_context

router = APIRouter(prefix="/asset-contracts", tags=["asset-contracts"])


def _quantize_usd(value: Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.000001"))


def _calculate_monthly_amortized(
    billing_cycle: str,
    monthly_fee_usd: Decimal | None,
    yearly_fee_usd: Decimal | None,
) -> Decimal:
    if billing_cycle == "MONTHLY":
        return _quantize_usd(monthly_fee_usd or Decimal("0"))
    if billing_cycle == "YEARLY":
        return _quantize_usd((yearly_fee_usd or Decimal("0")) / Decimal("12"))
    return Decimal("0")


def _validate_contract_payload(
    billing_cycle: str,
    monthly_fee_usd: Decimal | None,
    yearly_fee_usd: Decimal | None,
    start_date,
    end_date,
) -> None:
    if end_date is not None and end_date <= start_date:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="end_date 必須晚於 start_date")

    if monthly_fee_usd is not None and monthly_fee_usd < 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="monthly_fee_usd 不可為負")
    if yearly_fee_usd is not None and yearly_fee_usd < 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="yearly_fee_usd 不可為負")

    if billing_cycle == "MONTHLY":
        if monthly_fee_usd is None or yearly_fee_usd is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="MONTHLY 合約需填 monthly_fee_usd 且 yearly_fee_usd 必須為空",
            )
        return

    if billing_cycle == "YEARLY":
        if yearly_fee_usd is None or monthly_fee_usd is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="YEARLY 合約需填 yearly_fee_usd 且 monthly_fee_usd 必須為空",
            )
        return

    if billing_cycle == "USAGE_BASED":
        if monthly_fee_usd is not None or yearly_fee_usd is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="USAGE_BASED 合約不可填 monthly_fee_usd/yearly_fee_usd",
            )
        return

    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="不支援的 billing_cycle")


@router.get("", response_model=dict)
def list_asset_contracts(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
) -> dict:
    context = get_scope_context(current_user)
    allowed_ids = allowed_department_ids(db, context)

    stmt = (
        select(AssetContract)
        .outerjoin(ApiKey, AssetContract.api_key_id == ApiKey.id)
        .outerjoin(AIAccount, AssetContract.ai_account_id == AIAccount.id)
        .outerjoin(User, AIAccount.owner_user_id == User.id)
    )

    if allowed_ids is not None:
        stmt = stmt.where(or_(ApiKey.department_id.in_(allowed_ids), User.department_id.in_(allowed_ids)))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    order_column = AssetContract.created_at if pagination.sort_by == "created_at" else AssetContract.id
    ordering = asc(order_column) if pagination.sort_order == "asc" else desc(order_column)

    rows = db.scalars(
        stmt.order_by(ordering)
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    ).all()

    return {
        "items": [AssetContractRead.model_validate(row).model_dump() for row in rows],
        "meta": PaginationMeta(page=pagination.page, page_size=pagination.page_size, total=int(total)).model_dump(),
    }


@router.post("", response_model=AssetContractRead)
def create_asset_contract(
    payload: AssetContractCreate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.FINANCE.value)),
) -> AssetContractRead:
    if payload.api_key_id is not None:
        api_key = db.get(ApiKey, payload.api_key_id)
        if api_key is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    if payload.ai_account_id is not None:
        ai_account = db.get(AIAccount, payload.ai_account_id)
        if ai_account is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI account not found")

    _validate_contract_payload(
        billing_cycle=payload.billing_cycle,
        monthly_fee_usd=payload.monthly_fee_usd,
        yearly_fee_usd=payload.yearly_fee_usd,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )

    entity = AssetContract(
        api_key_id=payload.api_key_id,
        ai_account_id=payload.ai_account_id,
        billing_cycle=payload.billing_cycle,
        monthly_fee_usd=payload.monthly_fee_usd,
        yearly_fee_usd=payload.yearly_fee_usd,
        monthly_amortized_usd=_calculate_monthly_amortized(
            payload.billing_cycle,
            payload.monthly_fee_usd,
            payload.yearly_fee_usd,
        ),
        currency=payload.currency,
        start_date=payload.start_date,
        end_date=payload.end_date,
        auto_renew=payload.auto_renew,
        payment_method=payload.payment_method,
        status=payload.status,
        notes=payload.notes,
        created_by_user_id=actor.id,
    )
    db.add(entity)
    db.flush()

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="ASSET_CONTRACT_CREATE",
        resource_type="asset_contracts",
        resource_id=str(entity.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={
            "api_key_id": entity.api_key_id,
            "ai_account_id": entity.ai_account_id,
            "billing_cycle": entity.billing_cycle,
            "monthly_amortized_usd": str(entity.monthly_amortized_usd),
            "status": entity.status,
        },
    )

    db.commit()
    db.refresh(entity)
    return AssetContractRead.model_validate(entity)


@router.patch("/{contract_id}", response_model=AssetContractRead)
def patch_asset_contract(
    contract_id: int,
    payload: AssetContractUpdate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.FINANCE.value)),
) -> AssetContractRead:
    entity = db.get(AssetContract, contract_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset contract not found")

    before = {
        "billing_cycle": entity.billing_cycle,
        "monthly_fee_usd": str(entity.monthly_fee_usd) if entity.monthly_fee_usd is not None else None,
        "yearly_fee_usd": str(entity.yearly_fee_usd) if entity.yearly_fee_usd is not None else None,
        "monthly_amortized_usd": str(entity.monthly_amortized_usd),
        "status": entity.status,
        "start_date": entity.start_date.isoformat(),
        "end_date": entity.end_date.isoformat() if entity.end_date else None,
    }

    fields_set = payload.model_fields_set

    billing_cycle = entity.billing_cycle
    monthly_fee_usd = entity.monthly_fee_usd
    yearly_fee_usd = entity.yearly_fee_usd
    start_date = entity.start_date
    end_date = entity.end_date

    if "billing_cycle" in fields_set:
        if payload.billing_cycle is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="billing_cycle 不可為空")
        billing_cycle = payload.billing_cycle

    if "monthly_fee_usd" in fields_set:
        monthly_fee_usd = payload.monthly_fee_usd
    if "yearly_fee_usd" in fields_set:
        yearly_fee_usd = payload.yearly_fee_usd
    if "start_date" in fields_set:
        if payload.start_date is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="start_date 不可為空")
        start_date = payload.start_date
    if "end_date" in fields_set:
        end_date = payload.end_date

    _validate_contract_payload(
        billing_cycle=billing_cycle,
        monthly_fee_usd=monthly_fee_usd,
        yearly_fee_usd=yearly_fee_usd,
        start_date=start_date,
        end_date=end_date,
    )

    entity.billing_cycle = billing_cycle
    entity.monthly_fee_usd = monthly_fee_usd
    entity.yearly_fee_usd = yearly_fee_usd
    entity.start_date = start_date
    entity.end_date = end_date

    if "currency" in fields_set:
        if payload.currency is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="currency 不可為空")
        entity.currency = payload.currency
    if "auto_renew" in fields_set:
        if payload.auto_renew is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="auto_renew 不可為空")
        entity.auto_renew = payload.auto_renew
    if "payment_method" in fields_set:
        entity.payment_method = payload.payment_method
    if "status" in fields_set:
        if payload.status is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="status 不可為空")
        entity.status = payload.status
    if "notes" in fields_set:
        entity.notes = payload.notes

    entity.monthly_amortized_usd = _calculate_monthly_amortized(
        billing_cycle,
        monthly_fee_usd,
        yearly_fee_usd,
    )

    db.flush()

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="ASSET_CONTRACT_UPDATE",
        resource_type="asset_contracts",
        resource_id=str(entity.id),
        source="API",
        ip_address=None,
        before_json=before,
        after_json={
            "billing_cycle": entity.billing_cycle,
            "monthly_fee_usd": str(entity.monthly_fee_usd) if entity.monthly_fee_usd is not None else None,
            "yearly_fee_usd": str(entity.yearly_fee_usd) if entity.yearly_fee_usd is not None else None,
            "monthly_amortized_usd": str(entity.monthly_amortized_usd),
            "status": entity.status,
            "start_date": entity.start_date.isoformat(),
            "end_date": entity.end_date.isoformat() if entity.end_date else None,
        },
    )

    db.commit()
    db.refresh(entity)
    return AssetContractRead.model_validate(entity)
