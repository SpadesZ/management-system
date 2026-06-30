# File Path: backend/app/api/routers/ops.py
# Timestamp: 2026-05-26T22:30:00+08:00
# Version: v0.1

from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, desc, func, select

from app.api.deps import DBSessionDep, require_roles
from app.core.audit import write_audit_log
from app.models.entities import (
    AggregationJob,
    Alert,
    BillingReconciliationIssue,
    CostLedger,
    ExportJob,
    UsageEvent,
    User,
)
from app.models.enums import AlertStatus, JobStatus, RoleCode

router = APIRouter(prefix="/ops", tags=["ops"])


def _to_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _to_text(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def _time_window(start_at: datetime | None, end_at: datetime | None) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    start = start_at or datetime(now.year, now.month, 1, tzinfo=UTC)
    end = end_at or now
    return start, end


def _error_budget_severity(error_rate_pct: Decimal, target_pct: Decimal) -> str:
    if target_pct <= 0:
        return "CRITICAL"
    if error_rate_pct <= target_pct * Decimal("0.50"):
        return "LOW"
    if error_rate_pct <= target_pct:
        return "MEDIUM"
    if error_rate_pct <= target_pct * Decimal("2"):
        return "HIGH"
    return "CRITICAL"


@router.get("/billing-accuracy", response_model=dict)
def get_billing_accuracy(
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.FINANCE.value, RoleCode.SECURITY.value)),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    delta_threshold_usd: Decimal = Query(default=Decimal("0.050000"), ge=Decimal("0")),
) -> dict:
    _ = actor
    window_start, window_end = _time_window(start_at, end_at)

    usage_agg = (
        select(
            UsageEvent.request_id.label("request_id"),
            func.coalesce(func.sum(UsageEvent.estimated_cost_usd), 0).label("usage_estimated_cost"),
        )
        .where(
            UsageEvent.created_at >= window_start,
            UsageEvent.created_at < window_end,
        )
        .group_by(UsageEvent.request_id)
        .subquery()
    )

    ledger_row = db.execute(
        select(
            func.count(CostLedger.id),
            func.coalesce(func.sum(CostLedger.settled_cost), 0),
        ).where(
            CostLedger.created_at >= window_start,
            CostLedger.created_at < window_end,
        )
    ).one()

    usage_row = db.execute(
        select(
            func.count(UsageEvent.id),
            func.coalesce(func.sum(UsageEvent.estimated_cost_usd), 0),
        ).where(
            UsageEvent.created_at >= window_start,
            UsageEvent.created_at < window_end,
        )
    ).one()

    mismatch_row = db.execute(
        select(
            func.count(),
            func.coalesce(
                func.sum(
                    func.abs(CostLedger.settled_cost - usage_agg.c.usage_estimated_cost)
                ),
                0,
            ),
        )
        .select_from(CostLedger)
        .join(usage_agg, usage_agg.c.request_id == CostLedger.request_id)
        .where(
            CostLedger.created_at >= window_start,
            CostLedger.created_at < window_end,
            func.abs(CostLedger.settled_cost - usage_agg.c.usage_estimated_cost) >= delta_threshold_usd,
        )
    ).one()

    issue_open_count = db.scalar(
        select(func.count(BillingReconciliationIssue.id)).where(
            BillingReconciliationIssue.status.in_([JobStatus.PENDING.value, JobStatus.RUNNING.value])
        )
    ) or 0

    ledger_total = _to_decimal(ledger_row[1])
    usage_total = _to_decimal(usage_row[1])
    delta_total = ledger_total - usage_total
    baseline = max(ledger_total.copy_abs(), usage_total.copy_abs(), Decimal("0.000001"))
    accuracy_ratio = Decimal("1") - (delta_total.copy_abs() / baseline)

    return {
        "period": {
            "start_at": window_start.isoformat(),
            "end_at": window_end.isoformat(),
        },
        "ledger_request_count": int(ledger_row[0] or 0),
        "usage_request_count": int(usage_row[0] or 0),
        "ledger_settled_total_usd": _to_text(ledger_total),
        "usage_estimated_total_usd": _to_text(usage_total),
        "delta_total_usd": _to_text(delta_total),
        "mismatch_request_count": int(mismatch_row[0] or 0),
        "mismatch_amount_usd": _to_text(_to_decimal(mismatch_row[1])),
        "reconciliation_issue_open_count": int(issue_open_count),
        "accuracy_ratio": _to_text(accuracy_ratio),
    }


@router.get("/reconciliation/report", response_model=dict)
def get_reconciliation_report(
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.FINANCE.value, RoleCode.SECURITY.value)),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    delta_threshold_usd: Decimal = Query(default=Decimal("0.050000"), ge=Decimal("0")),
) -> dict:
    _ = actor
    window_start, window_end = _time_window(start_at, end_at)

    usage_agg = (
        select(
            UsageEvent.request_id.label("request_id"),
            func.coalesce(func.sum(UsageEvent.estimated_cost_usd), 0).label("usage_estimated_cost"),
            func.max(UsageEvent.created_at).label("usage_created_at"),
        )
        .where(
            UsageEvent.created_at >= window_start,
            UsageEvent.created_at < window_end,
        )
        .group_by(UsageEvent.request_id)
        .subquery()
    )

    delta_expr = CostLedger.settled_cost - usage_agg.c.usage_estimated_cost
    abs_delta_expr = func.abs(delta_expr)

    base_stmt = (
        select(
            CostLedger.request_id,
            CostLedger.idempotency_key,
            CostLedger.user_id,
            CostLedger.department_id,
            CostLedger.settled_cost,
            usage_agg.c.usage_estimated_cost,
            delta_expr.label("delta_cost"),
            abs_delta_expr.label("abs_delta"),
            CostLedger.created_at,
            usage_agg.c.usage_created_at,
        )
        .join(usage_agg, usage_agg.c.request_id == CostLedger.request_id)
        .where(
            CostLedger.created_at >= window_start,
            CostLedger.created_at < window_end,
            abs_delta_expr >= delta_threshold_usd,
        )
    )

    total = db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0

    rows = db.execute(
        base_stmt
        .order_by(desc(abs_delta_expr), desc(CostLedger.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    issue_status_rows = db.execute(
        select(BillingReconciliationIssue.status, func.count(BillingReconciliationIssue.id))
        .group_by(BillingReconciliationIssue.status)
    ).all()
    issue_status_counts = {str(row[0]): int(row[1] or 0) for row in issue_status_rows}

    return {
        "items": [
            {
                "request_id": str(row[0]),
                "idempotency_key": str(row[1]),
                "user_id": int(row[2]),
                "department_id": int(row[3]),
                "ledger_settled_cost_usd": _to_text(_to_decimal(row[4])),
                "usage_estimated_cost_usd": _to_text(_to_decimal(row[5])),
                "delta_cost_usd": _to_text(_to_decimal(row[6])),
                "abs_delta_usd": _to_text(_to_decimal(row[7])),
                "ledger_created_at": row[8].isoformat() if row[8] is not None else None,
                "usage_created_at": row[9].isoformat() if row[9] is not None else None,
            }
            for row in rows
        ],
        "meta": {
            "page": page,
            "page_size": page_size,
            "total": int(total),
            "delta_threshold_usd": _to_text(delta_threshold_usd),
        },
        "issue_status_counts": issue_status_counts,
    }


@router.get("/error-budget", response_model=dict)
def get_error_budget(
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.FINANCE.value, RoleCode.SECURITY.value)),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    error_budget_pct: Decimal = Query(default=Decimal("1.000000"), gt=Decimal("0"), le=Decimal("100")),
    emit_alert: bool = Query(default=False),
) -> dict:
    window_start, window_end = _time_window(start_at, end_at)

    usage_row = db.execute(
        select(
            func.count(UsageEvent.id),
            func.coalesce(
                func.sum(case((UsageEvent.status != "SUCCESS", 1), else_=0)),
                0,
            ),
        ).where(
            UsageEvent.created_at >= window_start,
            UsageEvent.created_at < window_end,
        )
    ).one()

    total_requests = int(usage_row[0] or 0)
    error_requests = int(usage_row[1] or 0)

    if total_requests > 0:
        error_rate_pct = (Decimal(error_requests) / Decimal(total_requests)) * Decimal("100")
    else:
        error_rate_pct = Decimal("0")

    severity = _error_budget_severity(error_rate_pct, error_budget_pct)
    remaining_budget_pct = max(Decimal("0"), error_budget_pct - error_rate_pct)
    consumed_budget_pct = min(
        Decimal("100"),
        (error_rate_pct / error_budget_pct) * Decimal("100") if error_budget_pct > 0 else Decimal("100"),
    )

    open_alert_rows = db.execute(
        select(Alert.severity, func.count(Alert.id))
        .where(Alert.status.in_([AlertStatus.OPEN.value, AlertStatus.ACKNOWLEDGED.value]))
        .group_by(Alert.severity)
    ).all()
    open_alert_distribution = {str(row[0]): int(row[1] or 0) for row in open_alert_rows}

    alert_emitted = False
    if emit_alert and severity in {"HIGH", "CRITICAL"}:
        title = f"Error budget burn {severity}"
        existing_open = db.scalar(
            select(Alert)
            .where(
                Alert.title == title,
                Alert.status.in_([AlertStatus.OPEN.value, AlertStatus.ACKNOWLEDGED.value]),
                Alert.triggered_at >= window_start,
                Alert.triggered_at < window_end,
            )
            .order_by(desc(Alert.triggered_at))
        )
        if existing_open is None:
            alert = Alert(
                rule_id=None,
                severity=severity,
                title=title,
                content=(
                    f"Error rate {error_rate_pct.quantize(Decimal('0.000001'))}% exceeded budget "
                    f"{error_budget_pct.quantize(Decimal('0.000001'))}% in period."
                ),
                status=AlertStatus.OPEN.value,
                scope_type="SYSTEM",
                scope_id=None,
                metadata_json={
                    "error_rate_pct": _to_text(error_rate_pct),
                    "error_budget_pct": _to_text(error_budget_pct),
                    "period_start_at": window_start.isoformat(),
                    "period_end_at": window_end.isoformat(),
                    "source": "ops.error_budget",
                },
            )
            db.add(alert)
            db.flush()
            write_audit_log(
                db,
                actor_user_id=actor.id,
                action="ERROR_BUDGET_ALERT_EMIT",
                resource_type="alerts",
                resource_id=str(alert.id),
                source="API",
                ip_address=None,
                before_json=None,
                after_json={
                    "severity": alert.severity,
                    "title": alert.title,
                },
            )
            db.commit()
            alert_emitted = True

    return {
        "period": {
            "start_at": window_start.isoformat(),
            "end_at": window_end.isoformat(),
        },
        "total_requests": total_requests,
        "error_requests": error_requests,
        "error_rate_pct": _to_text(error_rate_pct),
        "error_budget_pct": _to_text(error_budget_pct),
        "remaining_budget_pct": _to_text(remaining_budget_pct),
        "consumed_budget_pct": _to_text(consumed_budget_pct),
        "severity": severity,
        "open_alert_distribution": open_alert_distribution,
        "alert_emitted": alert_emitted,
    }


@router.get("/worker/backlog", response_model=dict)
def get_worker_backlog(
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.FINANCE.value, RoleCode.SECURITY.value)),
) -> dict:
    _ = actor
    now = datetime.now(UTC)

    export_status_rows = db.execute(
        select(ExportJob.status, func.count(ExportJob.id)).group_by(ExportJob.status)
    ).all()
    aggregation_status_rows = db.execute(
        select(AggregationJob.status, func.count(AggregationJob.id)).group_by(AggregationJob.status)
    ).all()

    export_status_counts = {str(row[0]): int(row[1] or 0) for row in export_status_rows}
    aggregation_status_counts = {str(row[0]): int(row[1] or 0) for row in aggregation_status_rows}

    oldest_export_pending = db.scalar(
        select(ExportJob.created_at)
        .where(ExportJob.status == JobStatus.PENDING.value)
        .order_by(ExportJob.created_at)
        .limit(1)
    )
    oldest_aggregation_pending = db.scalar(
        select(AggregationJob.created_at)
        .where(AggregationJob.status == JobStatus.PENDING.value)
        .order_by(AggregationJob.created_at)
        .limit(1)
    )

    backlog_ages = []
    if oldest_export_pending is not None:
        backlog_ages.append(max(0, int((now - oldest_export_pending).total_seconds())))
    if oldest_aggregation_pending is not None:
        backlog_ages.append(max(0, int((now - oldest_aggregation_pending).total_seconds())))

    export_failed_rows = db.execute(
        select(ExportJob.id, ExportJob.error_message, ExportJob.finished_at)
        .where(ExportJob.status == JobStatus.FAILED.value)
        .order_by(desc(ExportJob.finished_at), desc(ExportJob.id))
        .limit(20)
    ).all()
    aggregation_failed_rows = db.execute(
        select(AggregationJob.id, AggregationJob.error_message, AggregationJob.finished_at)
        .where(AggregationJob.status == JobStatus.FAILED.value)
        .order_by(desc(AggregationJob.finished_at), desc(AggregationJob.id))
        .limit(20)
    ).all()

    dead_letters = [
        {
            "queue": "export_jobs",
            "id": int(row[0]),
            "error_message": str(row[1] or ""),
            "finished_at": row[2].isoformat() if row[2] is not None else None,
        }
        for row in export_failed_rows
    ] + [
        {
            "queue": "aggregation_jobs",
            "id": int(row[0]),
            "error_message": str(row[1] or ""),
            "finished_at": row[2].isoformat() if row[2] is not None else None,
        }
        for row in aggregation_failed_rows
    ]

    pending_total = int(export_status_counts.get(JobStatus.PENDING.value, 0)) + int(
        aggregation_status_counts.get(JobStatus.PENDING.value, 0)
    )
    running_total = int(export_status_counts.get(JobStatus.RUNNING.value, 0)) + int(
        aggregation_status_counts.get(JobStatus.RUNNING.value, 0)
    )
    failed_total = int(export_status_counts.get(JobStatus.FAILED.value, 0)) + int(
        aggregation_status_counts.get(JobStatus.FAILED.value, 0)
    )

    return {
        "generated_at": now.isoformat(),
        "queue_depth": {
            "pending_total": pending_total,
            "running_total": running_total,
            "failed_total": failed_total,
            "max_pending_age_seconds": max(backlog_ages) if backlog_ages else 0,
        },
        "export_jobs": export_status_counts,
        "aggregation_jobs": aggregation_status_counts,
        "dead_letter_candidates": dead_letters,
    }
