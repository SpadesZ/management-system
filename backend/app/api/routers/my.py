# File Path: backend/app/api/routers/my.py
# Timestamp: 2026-05-26T21:20:00+08:00
# Version: v0.1

from fastapi import APIRouter, Depends, Query
from sqlalchemy import asc, desc, func, select

from app.api.deps import CurrentUserDep, DBSessionDep, get_pagination_query
from app.models.entities import (
    AIAccount,
    AIAccountAccessGrant,
    AIAccountAssignment,
    ApiKey,
    ApprovalRequest,
    WorkOutput,
)
from app.schemas.ai_account import AIAccountRead
from app.schemas.api_key import APIKeyRead
from app.schemas.approval import ApprovalRequestRead
from app.schemas.common import PaginationMeta, PaginationQuery
from app.schemas.work_output import WorkOutputRead

router = APIRouter(prefix="/my", tags=["my"])


def _normalize_status(value: str | None) -> str | None:
    text = str(value or "").strip().upper()
    return text or None


@router.get("/assets", response_model=dict)
def list_my_assets(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
) -> dict:
    api_key_stmt = select(ApiKey).where(ApiKey.owner_user_id == current_user.id)
    api_keys_total = db.scalar(select(func.count()).select_from(api_key_stmt.subquery())) or 0

    api_key_order_column = ApiKey.created_at if pagination.sort_by == "created_at" else ApiKey.id
    api_key_ordering = asc(api_key_order_column) if pagination.sort_order == "asc" else desc(api_key_order_column)
    api_keys = db.scalars(
        api_key_stmt.order_by(api_key_ordering)
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    ).all()

    granted_account_id_rows = db.execute(
        select(AIAccountAccessGrant.ai_account_id)
        .where(
            AIAccountAccessGrant.user_id == current_user.id,
            AIAccountAccessGrant.status == "ACTIVE",
        )
        .distinct()
    ).all()
    granted_account_ids = {int(row[0]) for row in granted_account_id_rows}

    legacy_assignment_rows = db.execute(
        select(AIAccountAssignment.ai_account_id)
        .where(
            AIAccountAssignment.user_id == current_user.id,
            AIAccountAssignment.status == "ACTIVE",
        )
        .distinct()
    ).all()
    granted_account_ids.update(int(row[0]) for row in legacy_assignment_rows)

    account_stmt = select(AIAccount).where(AIAccount.owner_user_id == current_user.id)
    if granted_account_ids:
        account_stmt = account_stmt.union(select(AIAccount).where(AIAccount.id.in_(sorted(granted_account_ids))))

    account_subquery = account_stmt.subquery()
    ai_accounts_total = db.scalar(select(func.count()).select_from(account_subquery)) or 0

    if pagination.sort_by == "created_at":
        account_order_column = account_subquery.c.created_at
    else:
        account_order_column = account_subquery.c.id
    account_ordering = asc(account_order_column) if pagination.sort_order == "asc" else desc(account_order_column)

    ai_accounts = db.scalars(
        select(AIAccount)
        .join(account_subquery, account_subquery.c.id == AIAccount.id)
        .order_by(account_ordering)
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    ).all()

    return {
        "api_keys": [APIKeyRead.model_validate(row).model_dump(mode="json") for row in api_keys],
        "ai_accounts": [AIAccountRead.model_validate(row).model_dump(mode="json") for row in ai_accounts],
        "meta": {
            "page": pagination.page,
            "page_size": pagination.page_size,
            "api_keys_total": int(api_keys_total),
            "ai_accounts_total": int(ai_accounts_total),
        },
    }


@router.get("/requests", response_model=dict)
def list_my_requests(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
    status_filter: str | None = Query(default=None, alias="status"),
) -> dict:
    stmt = select(ApprovalRequest).where(ApprovalRequest.requester_id == current_user.id)

    normalized_status = _normalize_status(status_filter)
    if normalized_status is not None:
        stmt = stmt.where(ApprovalRequest.status == normalized_status)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    order_column = ApprovalRequest.submitted_at if pagination.sort_by == "submitted_at" else ApprovalRequest.id
    ordering = asc(order_column) if pagination.sort_order == "asc" else desc(order_column)

    rows = db.scalars(
        stmt.order_by(ordering)
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    ).all()

    return {
        "items": [ApprovalRequestRead.model_validate(row).model_dump(mode="json") for row in rows],
        "meta": PaginationMeta(page=pagination.page, page_size=pagination.page_size, total=int(total)).model_dump(),
    }


@router.get("/outputs", response_model=dict)
def list_my_outputs(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
    status_filter: str | None = Query(default=None, alias="status"),
    usage_purpose_id: int | None = Query(default=None),
) -> dict:
    stmt = select(WorkOutput).where(WorkOutput.user_id == current_user.id)

    normalized_status = _normalize_status(status_filter)
    if normalized_status is not None:
        stmt = stmt.where(WorkOutput.status == normalized_status)

    if usage_purpose_id is not None:
        stmt = stmt.where(WorkOutput.usage_purpose_id == usage_purpose_id)

    if pagination.start_at is not None:
        stmt = stmt.where(WorkOutput.created_at >= pagination.start_at)
    if pagination.end_at is not None:
        stmt = stmt.where(WorkOutput.created_at <= pagination.end_at)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    if pagination.sort_by == "created_at":
        order_column = WorkOutput.created_at
    elif pagination.sort_by == "status":
        order_column = WorkOutput.status
    else:
        order_column = WorkOutput.id

    ordering = asc(order_column) if pagination.sort_order == "asc" else desc(order_column)
    rows = db.scalars(
        stmt.order_by(ordering)
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    ).all()

    return {
        "items": [WorkOutputRead.model_validate(row).model_dump(mode="json") for row in rows],
        "meta": PaginationMeta(page=pagination.page, page_size=pagination.page_size, total=int(total)).model_dump(),
    }
