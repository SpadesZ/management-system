# File Path: backend/app/services/budget.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import ApiKeyEntitlement, BudgetReservation, CostLedger, Department, ProjectBudget
from app.models.enums import ReservationStatus


@dataclass
class LimitItem:
    label: str
    soft_limit: Decimal | None
    hard_limit: Decimal | None
    current_spend: Decimal


@dataclass
class BudgetCheckResult:
    allowed: bool
    effective_soft_limit: Decimal | None
    effective_hard_limit: Decimal | None
    current_spend: Decimal
    estimated_cost: Decimal
    remaining_budget: Decimal
    rejection_reason: str | None
    soft_limit_exceeded: bool
    hard_limit_exceeded: bool


def _month_range(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now or datetime.now(UTC)
    month_start = datetime(current.year, current.month, 1, tzinfo=UTC)
    month_end = month_start + relativedelta(months=1)
    return month_start, month_end


def _sum_cost(
    db: Session,
    *,
    user_id: int | None = None,
    department_id: int | None = None,
    project_id: int | None = None,
) -> Decimal:
    month_start, month_end = _month_range()
    stmt = select(func.coalesce(func.sum(CostLedger.settled_cost), 0)).where(
        CostLedger.created_at >= month_start,
        CostLedger.created_at < month_end,
    )
    if user_id is not None:
        stmt = stmt.where(CostLedger.user_id == user_id)
    if department_id is not None:
        stmt = stmt.where(CostLedger.department_id == department_id)
    if project_id is not None:
        stmt = stmt.where(CostLedger.project_id == project_id)
    value = db.scalar(stmt)
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _active_project_budget(db: Session, project_id: int | None) -> ProjectBudget | None:
    if project_id is None:
        return None
    now = datetime.now(UTC)
    stmt = select(ProjectBudget).where(
        ProjectBudget.project_id == project_id,
        ProjectBudget.effective_from <= now,
        func.coalesce(ProjectBudget.effective_to, now + relativedelta(years=100)) > now,
    )
    return db.scalar(stmt)


def _entitlement_limit(db: Session, subject_type: str, subject_id: int) -> tuple[Decimal | None, Decimal | None]:
    stmt = select(ApiKeyEntitlement).where(
        ApiKeyEntitlement.subject_type == subject_type,
        ApiKeyEntitlement.subject_id == subject_id,
        ApiKeyEntitlement.status == "ACTIVE",
    )
    ent = db.scalar(stmt)
    if ent is None:
        return None, None
    return ent.monthly_soft_limit_usd, ent.monthly_hard_limit_usd


def evaluate_budget(
    db: Session,
    *,
    user_id: int,
    department_id: int,
    project_id: int | None,
    api_key_id: int,
    estimated_cost: Decimal,
) -> BudgetCheckResult:
    settings = get_settings()
    limits: list[LimitItem] = []

    user_soft, user_hard = _entitlement_limit(db, "USER", user_id)
    limits.append(
        LimitItem(
            label="user",
            soft_limit=user_soft,
            hard_limit=user_hard,
            current_spend=_sum_cost(db, user_id=user_id),
        )
    )

    dept = db.get(Department, department_id)
    dept_hard = dept.monthly_budget_usd if dept is not None else Decimal(str(settings.default_hard_limit_usd))
    dept_soft = (dept_hard * Decimal("0.9")).quantize(Decimal("0.000001"))
    limits.append(
        LimitItem(
            label="department",
            soft_limit=dept_soft,
            hard_limit=dept_hard,
            current_spend=_sum_cost(db, department_id=department_id),
        )
    )

    project_budget = _active_project_budget(db, project_id)
    if project_budget is not None:
        limits.append(
            LimitItem(
                label="project",
                soft_limit=project_budget.monthly_soft_limit_usd,
                hard_limit=project_budget.monthly_hard_limit_usd,
                current_spend=_sum_cost(db, project_id=project_id),
            )
        )

    key_soft, key_hard = _entitlement_limit(db, "API_KEY", api_key_id)
    limits.append(
        LimitItem(
            label="api_key",
            soft_limit=key_soft,
            hard_limit=key_hard,
            current_spend=_sum_cost(db, department_id=department_id),
        )
    )

    soft_candidates = [item.soft_limit for item in limits if item.soft_limit is not None]
    hard_candidates = [item.hard_limit for item in limits if item.hard_limit is not None]

    effective_soft = min(soft_candidates) if soft_candidates else Decimal(str(settings.default_soft_limit_usd))
    effective_hard = min(hard_candidates) if hard_candidates else Decimal(str(settings.default_hard_limit_usd))

    hard_exceeded = False
    soft_exceeded = False
    for item in limits:
        projected = item.current_spend + estimated_cost
        if item.hard_limit is not None and projected > item.hard_limit:
            hard_exceeded = True
        if item.soft_limit is not None and projected > item.soft_limit:
            soft_exceeded = True

    baseline_spend = max((item.current_spend for item in limits), default=Decimal("0"))
    remaining_budget = max(Decimal("0"), effective_hard - baseline_spend)

    if hard_exceeded:
        return BudgetCheckResult(
            allowed=False,
            effective_soft_limit=effective_soft,
            effective_hard_limit=effective_hard,
            current_spend=baseline_spend,
            estimated_cost=estimated_cost,
            remaining_budget=remaining_budget,
            rejection_reason="BUDGET_HARD_LIMIT_EXCEEDED",
            soft_limit_exceeded=soft_exceeded,
            hard_limit_exceeded=True,
        )

    return BudgetCheckResult(
        allowed=True,
        effective_soft_limit=effective_soft,
        effective_hard_limit=effective_hard,
        current_spend=baseline_spend,
        estimated_cost=estimated_cost,
        remaining_budget=remaining_budget,
        rejection_reason=None,
        soft_limit_exceeded=soft_exceeded,
        hard_limit_exceeded=False,
    )


def create_reservation(
    db: Session,
    *,
    request_id: str,
    user_id: int,
    department_id: int,
    project_id: int | None,
    estimated_cost: Decimal,
    currency: str,
) -> BudgetReservation:
    insert_stmt = (
        pg_insert(BudgetReservation)
        .values(
            request_id=request_id,
            user_id=user_id,
            department_id=department_id,
            project_id=project_id,
            currency=currency,
            estimated_cost=estimated_cost,
            reserved_amount=estimated_cost,
            status=ReservationStatus.RESERVED.value,
        )
        .on_conflict_do_nothing(index_elements=[BudgetReservation.request_id])
        .returning(BudgetReservation.id)
    )
    inserted_id = db.scalar(insert_stmt)
    if inserted_id is not None:
        created = db.get(BudgetReservation, inserted_id)
        if created is not None:
            return created

    existing = db.scalar(select(BudgetReservation).where(BudgetReservation.request_id == request_id))
    if existing is not None:
        return existing

    raise RuntimeError("Failed to create or load budget reservation")


def _get_reservation_for_update(db: Session, request_id: str) -> BudgetReservation | None:
    return db.scalar(
        select(BudgetReservation)
        .where(BudgetReservation.request_id == request_id)
        .with_for_update()
    )


def settle_reservation(db: Session, request_id: str, settled_amount: Decimal) -> None:
    reservation = _get_reservation_for_update(db, request_id)
    if reservation is None:
        return

    if reservation.status in {ReservationStatus.SETTLED.value, ReservationStatus.RELEASED.value}:
        return

    reservation.settled_amount = settled_amount
    reservation.status = ReservationStatus.SETTLED.value
    reservation.reconciled_at = datetime.now(UTC)


def release_reservation(db: Session, request_id: str) -> None:
    reservation = _get_reservation_for_update(db, request_id)
    if reservation is None:
        return

    if reservation.status == ReservationStatus.SETTLED.value:
        return
    if reservation.status == ReservationStatus.RELEASED.value:
        return

    reservation.settled_amount = Decimal("0")
    reservation.status = ReservationStatus.RELEASED.value
    reservation.reconciled_at = datetime.now(UTC)


def mark_pending_reconciliation(db: Session, request_id: str) -> None:
    reservation = _get_reservation_for_update(db, request_id)
    if reservation is None:
        return

    if reservation.status in {ReservationStatus.SETTLED.value, ReservationStatus.RELEASED.value}:
        return

    reservation.status = ReservationStatus.PENDING_RECONCILIATION.value
