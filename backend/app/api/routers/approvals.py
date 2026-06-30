# File Path: backend/app/api/routers/approvals.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc, func, select

from app.api.deps import CurrentUserDep, DBSessionDep, get_pagination_query, require_roles
from app.core.audit import write_audit_log
from app.models.entities import ApprovalRequest, ApprovalStep, User
from app.models.enums import ApprovalStatus, RoleCode
from app.schemas.approval import ApprovalDecisionRequest, ApprovalRequestCreate, ApprovalRequestRead
from app.schemas.common import PaginationMeta, PaginationQuery

router = APIRouter(prefix="/approval-requests", tags=["approval-requests"])


@router.get("", response_model=dict)
def list_approval_requests(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
) -> dict:
    stmt = select(ApprovalRequest)
    if current_user.role not in {RoleCode.ADMIN.value, RoleCode.MANAGER.value, RoleCode.FINANCE.value}:
        stmt = stmt.where(ApprovalRequest.requester_id == current_user.id)

    normalized_status = str(status_filter or "").strip().upper()
    if normalized_status:
        allowed_statuses = {
            ApprovalStatus.PENDING.value,
            ApprovalStatus.APPROVED.value,
            ApprovalStatus.REJECTED.value,
            ApprovalStatus.CANCELLED.value,
        }
        if normalized_status not in allowed_statuses:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid approval status filter")
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
        "items": [ApprovalRequestRead.model_validate(row).model_dump() for row in rows],
        "meta": PaginationMeta(page=pagination.page, page_size=pagination.page_size, total=int(total)).model_dump(),
    }


@router.post("", response_model=ApprovalRequestRead)
def create_approval_request(
    payload: ApprovalRequestCreate,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> ApprovalRequestRead:
    request = ApprovalRequest(
        requester_id=current_user.id,
        request_type=payload.request_type,
        target_type=payload.target_type,
        target_id=payload.target_id,
        reason=payload.reason,
        payload_json=payload.payload_json,
        status=ApprovalStatus.PENDING.value,
    )
    db.add(request)
    db.flush()

    step = ApprovalStep(
        request_id=request.id,
        step_no=1,
        approver_user_id=current_user.manager_id or current_user.id,
        approver_role=RoleCode.MANAGER.value,
        status=ApprovalStatus.PENDING.value,
    )
    db.add(step)

    write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="APPROVAL_REQUEST_CREATE",
        resource_type="approval_requests",
        resource_id=str(request.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={"request_type": request.request_type, "target_type": request.target_type},
    )

    db.commit()
    db.refresh(request)
    return ApprovalRequestRead.model_validate(request)


@router.post("/{request_id}/approve", response_model=ApprovalRequestRead)
def approve_request(
    request_id: int,
    payload: ApprovalDecisionRequest,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.MANAGER.value, RoleCode.FINANCE.value)),
) -> ApprovalRequestRead:
    request = db.get(ApprovalRequest, request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    step = db.scalar(
        select(ApprovalStep)
        .where(ApprovalStep.request_id == request_id, ApprovalStep.status == ApprovalStatus.PENDING.value)
        .order_by(ApprovalStep.step_no)
    )
    if step is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No pending approval step")

    if step.approver_user_id != actor.id and actor.role != RoleCode.ADMIN.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not approver")

    step.status = ApprovalStatus.APPROVED.value
    step.decision_reason = payload.decision_reason
    step.decided_at = datetime.now(UTC)

    request.status = ApprovalStatus.APPROVED.value
    request.resolved_at = datetime.now(UTC)

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="APPROVAL_REQUEST_APPROVE",
        resource_type="approval_requests",
        resource_id=str(request.id),
        source="API",
        ip_address=None,
        before_json={"status": ApprovalStatus.PENDING.value},
        after_json={"status": request.status, "decision_reason": payload.decision_reason},
    )

    db.commit()
    db.refresh(request)
    return ApprovalRequestRead.model_validate(request)


@router.post("/{request_id}/reject", response_model=ApprovalRequestRead)
def reject_request(
    request_id: int,
    payload: ApprovalDecisionRequest,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.MANAGER.value, RoleCode.FINANCE.value)),
) -> ApprovalRequestRead:
    request = db.get(ApprovalRequest, request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    step = db.scalar(
        select(ApprovalStep)
        .where(ApprovalStep.request_id == request_id, ApprovalStep.status == ApprovalStatus.PENDING.value)
        .order_by(ApprovalStep.step_no)
    )
    if step is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No pending approval step")

    if step.approver_user_id != actor.id and actor.role != RoleCode.ADMIN.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not approver")

    step.status = ApprovalStatus.REJECTED.value
    step.decision_reason = payload.decision_reason
    step.decided_at = datetime.now(UTC)

    request.status = ApprovalStatus.REJECTED.value
    request.resolved_at = datetime.now(UTC)

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="APPROVAL_REQUEST_REJECT",
        resource_type="approval_requests",
        resource_id=str(request.id),
        source="API",
        ip_address=None,
        before_json={"status": ApprovalStatus.PENDING.value},
        after_json={"status": request.status, "decision_reason": payload.decision_reason},
    )

    db.commit()
    db.refresh(request)
    return ApprovalRequestRead.model_validate(request)


@router.post("/{request_id}/return", response_model=ApprovalRequestRead)
def return_request(
    request_id: int,
    payload: ApprovalDecisionRequest,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.MANAGER.value, RoleCode.FINANCE.value)),
) -> ApprovalRequestRead:
    request = db.get(ApprovalRequest, request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    step = db.scalar(
        select(ApprovalStep)
        .where(ApprovalStep.request_id == request_id, ApprovalStep.status == ApprovalStatus.PENDING.value)
        .order_by(ApprovalStep.step_no)
    )
    if step is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No pending approval step")

    if step.approver_user_id != actor.id and actor.role != RoleCode.ADMIN.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not approver")

    step.status = ApprovalStatus.CANCELLED.value
    step.decision_reason = payload.decision_reason
    step.decided_at = datetime.now(UTC)

    request.status = ApprovalStatus.CANCELLED.value
    request.resolved_at = datetime.now(UTC)

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="APPROVAL_REQUEST_RETURN",
        resource_type="approval_requests",
        resource_id=str(request.id),
        source="API",
        ip_address=None,
        before_json={"status": ApprovalStatus.PENDING.value},
        after_json={"status": request.status, "decision_reason": payload.decision_reason},
    )

    db.commit()
    db.refresh(request)
    return ApprovalRequestRead.model_validate(request)
