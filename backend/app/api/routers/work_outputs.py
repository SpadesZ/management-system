# File Path: backend/app/api/routers/work_outputs.py
# Timestamp: 2026-05-26T12:00:00+08:00
# Version: v0.1

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc, func, select

from app.api.deps import CurrentUserDep, DBSessionDep, get_pagination_query, require_roles
from app.core.audit import write_audit_log
from app.models.entities import AIAccount, ApiKey, CostLedger, UsagePurpose, User, WorkOutput
from app.models.enums import RoleCode
from app.schemas.common import PaginationMeta, PaginationQuery
from app.schemas.work_output import WorkOutputCreate, WorkOutputDecisionRequest, WorkOutputRead
from app.services.scope_filter import (
    allowed_department_ids,
    apply_department_scope,
    ensure_resource_scope,
    get_scope_context,
)

router = APIRouter(prefix="/work-outputs", tags=["work-outputs"])


def _normalize_status(value: str | None) -> str | None:
    text = str(value or "").strip().upper()
    return text or None


def _resolve_department_id(db: DBSessionDep, payload: WorkOutputCreate, current_user: User) -> int:
    if payload.api_key_id is not None:
        api_key = db.get(ApiKey, payload.api_key_id)
        if api_key is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

        if payload.department_id is not None and int(payload.department_id) != int(api_key.department_id):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="department_id 與 api_key 的 department 不一致",
            )
        return int(api_key.department_id)

    ai_account = db.get(AIAccount, payload.ai_account_id)
    if ai_account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI account not found")

    owner = db.get(User, ai_account.owner_user_id)
    owner_department_id = int(owner.department_id) if owner is not None else None

    if payload.department_id is not None and owner_department_id is not None and int(payload.department_id) != owner_department_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="department_id 與 ai_account owner department 不一致",
        )

    if payload.department_id is not None:
        return int(payload.department_id)
    if owner_department_id is not None:
        return owner_department_id
    return int(current_user.department_id)


def _assert_scope_or_403(db: DBSessionDep, current_user: User, department_id: int) -> None:
    context = get_scope_context(current_user)
    allowed_ids = allowed_department_ids(db, context)
    if not ensure_resource_scope(department_id, allowed_ids):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission for this department scope")


def _get_work_output_or_404(db: DBSessionDep, work_output_id: int) -> WorkOutput:
    entity = db.get(WorkOutput, work_output_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work output not found")
    return entity


@router.get("", response_model=dict)
def list_work_outputs(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
    status_filter: str | None = Query(default=None, alias="status"),
    usage_purpose_id: int | None = Query(default=None),
) -> dict:
    context = get_scope_context(current_user)
    allowed_ids = allowed_department_ids(db, context)

    stmt = select(WorkOutput)
    stmt = apply_department_scope(stmt, WorkOutput.department_id, allowed_ids)

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


@router.post("", response_model=WorkOutputRead)
def create_work_output(
    payload: WorkOutputCreate,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> WorkOutputRead:
    usage_purpose = db.get(UsagePurpose, payload.usage_purpose_id)
    if usage_purpose is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usage purpose not found")

    if usage_purpose.status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Usage purpose is not active")

    department_id = _resolve_department_id(db, payload, current_user)
    _assert_scope_or_403(db, current_user, department_id)

    request_id = payload.request_id
    if payload.cost_ledger_id is not None:
        ledger = db.get(CostLedger, payload.cost_ledger_id)
        if ledger is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cost ledger not found")

        if request_id is not None and str(ledger.request_id) != str(request_id):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="request_id 與 cost_ledger.request_id 不一致",
            )
        request_id = str(ledger.request_id)

    entity = WorkOutput(
        usage_purpose_id=payload.usage_purpose_id,
        user_id=current_user.id,
        department_id=department_id,
        project_id=payload.project_id,
        api_key_id=payload.api_key_id,
        ai_account_id=payload.ai_account_id,
        cost_ledger_id=payload.cost_ledger_id,
        request_id=request_id,
        output_title=payload.output_title.strip(),
        output_summary=payload.output_summary,
        input_tokens=payload.input_tokens,
        output_tokens=payload.output_tokens,
        total_tokens=payload.total_tokens if payload.total_tokens is not None else payload.input_tokens + payload.output_tokens,
        cost_usd=payload.cost_usd,
        value_usd=payload.value_usd,
        currency=payload.currency,
        status="DRAFT",
        metadata_json=payload.metadata_json,
    )
    db.add(entity)
    db.flush()

    write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="WORK_OUTPUT_CREATE",
        resource_type="work_outputs",
        resource_id=str(entity.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={
            "usage_purpose_id": entity.usage_purpose_id,
            "department_id": entity.department_id,
            "api_key_id": entity.api_key_id,
            "ai_account_id": entity.ai_account_id,
            "status": entity.status,
            "cost_usd": str(entity.cost_usd),
            "value_usd": str(entity.value_usd),
        },
    )

    db.commit()
    db.refresh(entity)
    return WorkOutputRead.model_validate(entity)


@router.post("/{work_output_id}/submit", response_model=WorkOutputRead)
def submit_work_output(
    work_output_id: int,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> WorkOutputRead:
    entity = _get_work_output_or_404(db, work_output_id)
    _assert_scope_or_403(db, current_user, int(entity.department_id))

    privileged_roles = {RoleCode.ADMIN.value, RoleCode.FINANCE.value, RoleCode.MANAGER.value}
    if current_user.role not in privileged_roles and int(entity.user_id) != int(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner can submit this work output")

    if entity.status not in {"DRAFT", "REJECTED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Work output cannot be submitted in current status")

    before_status = entity.status
    entity.status = "SUBMITTED"
    entity.submitted_at = datetime.now(UTC)
    entity.resolved_at = None
    entity.reviewer_user_id = None
    entity.review_comment = None
    db.flush()

    write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="WORK_OUTPUT_SUBMIT",
        resource_type="work_outputs",
        resource_id=str(entity.id),
        source="API",
        ip_address=None,
        before_json={"status": before_status},
        after_json={"status": entity.status, "submitted_at": entity.submitted_at.isoformat() if entity.submitted_at else None},
    )

    db.commit()
    db.refresh(entity)
    return WorkOutputRead.model_validate(entity)


@router.post("/{work_output_id}/approve", response_model=WorkOutputRead)
def approve_work_output(
    work_output_id: int,
    payload: WorkOutputDecisionRequest,
    db: DBSessionDep,
    reviewer: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.FINANCE.value, RoleCode.MANAGER.value)),
) -> WorkOutputRead:
    entity = _get_work_output_or_404(db, work_output_id)
    _assert_scope_or_403(db, reviewer, int(entity.department_id))

    if entity.status != "SUBMITTED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only SUBMITTED work output can be approved")

    if int(entity.user_id) == int(reviewer.id) and reviewer.role != RoleCode.ADMIN.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reviewer cannot approve own work output")

    entity.status = "APPROVED"
    entity.reviewer_user_id = reviewer.id
    entity.review_comment = payload.review_comment
    entity.resolved_at = datetime.now(UTC)
    db.flush()

    write_audit_log(
        db,
        actor_user_id=reviewer.id,
        action="WORK_OUTPUT_APPROVE",
        resource_type="work_outputs",
        resource_id=str(entity.id),
        source="API",
        ip_address=None,
        before_json={"status": "SUBMITTED"},
        after_json={
            "status": entity.status,
            "review_comment": entity.review_comment,
            "resolved_at": entity.resolved_at.isoformat() if entity.resolved_at else None,
        },
    )

    db.commit()
    db.refresh(entity)
    return WorkOutputRead.model_validate(entity)


@router.post("/{work_output_id}/reject", response_model=WorkOutputRead)
def reject_work_output(
    work_output_id: int,
    payload: WorkOutputDecisionRequest,
    db: DBSessionDep,
    reviewer: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.FINANCE.value, RoleCode.MANAGER.value)),
) -> WorkOutputRead:
    entity = _get_work_output_or_404(db, work_output_id)
    _assert_scope_or_403(db, reviewer, int(entity.department_id))

    if entity.status != "SUBMITTED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only SUBMITTED work output can be rejected")

    entity.status = "REJECTED"
    entity.reviewer_user_id = reviewer.id
    entity.review_comment = payload.review_comment
    entity.resolved_at = datetime.now(UTC)
    db.flush()

    write_audit_log(
        db,
        actor_user_id=reviewer.id,
        action="WORK_OUTPUT_REJECT",
        resource_type="work_outputs",
        resource_id=str(entity.id),
        source="API",
        ip_address=None,
        before_json={"status": "SUBMITTED"},
        after_json={
            "status": entity.status,
            "review_comment": entity.review_comment,
            "resolved_at": entity.resolved_at.isoformat() if entity.resolved_at else None,
        },
    )

    db.commit()
    db.refresh(entity)
    return WorkOutputRead.model_validate(entity)
