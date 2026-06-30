# File Path: backend/app/api/routers/gateway.py
# Timestamp: 2026-05-26T12:00:00+08:00
# Version: v0.2

import hashlib
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.deps import CurrentUserDep, DBSessionDep
from app.core.audit import write_audit_log
from app.core.errors import (
    BUDGET_HARD_LIMIT_EXCEEDED,
    ENTITLEMENT_DENIED,
    ENTITLEMENT_MODEL_NOT_ALLOWED,
    MODEL_PRICE_NOT_FOUND,
    RATE_LIMIT_EXCEEDED,
)
from app.core.security import security_manager
from app.models.entities import ApiKey, CostLedger, GatewayRequest, Model, Provider, UsageEvent, UsageEventRequestKey
from app.models.enums import GatewayRequestStatus, LedgerType
from app.schemas.gateway import GatewayChatRequest, GatewayChatResponse, UsageInfo
from app.services.budget import (
    create_reservation,
    evaluate_budget,
    mark_pending_reconciliation,
    release_reservation,
    settle_reservation,
)
from app.services.entitlements import evaluate_api_key_entitlement
from app.services.gateway_provider import ProviderCallError, ProviderGatewayClient
from app.services.pricing import calculate_estimated_cost, estimate_tokens_from_text, get_active_model_price
from app.services.rate_limit import check_rpm_limit
from app.services.resource_limits import recompute_limit_state

router = APIRouter(tags=["gateway"])
provider_client = ProviderGatewayClient()


def _next_usage_event_id(db: DBSessionDep) -> int:
    next_id = db.scalar(select(text("nextval('usage_events_id_seq'::regclass)")))
    if next_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "USAGE_EVENT_SEQUENCE_UNAVAILABLE",
                "message": "Failed to allocate usage event id.",
                "retryable": False,
            },
        )
    return int(next_id)


@router.post("/gateway/chat", response_model=GatewayChatResponse)
async def gateway_chat(payload: GatewayChatRequest, db: DBSessionDep, current_user: CurrentUserDep) -> GatewayChatResponse:
    existing_request = db.scalar(
        select(GatewayRequest).where(
            or_(
                GatewayRequest.request_id == payload.request_id,
                (GatewayRequest.idempotency_key == payload.idempotency_key) & (GatewayRequest.user_id == current_user.id),
            )
        )
    )

    if existing_request is not None:
        if existing_request.status == GatewayRequestStatus.SUCCESS.value and existing_request.raw_response_json:
            replay = dict(existing_request.raw_response_json)
            replay["idempotent_replay"] = True
            return GatewayChatResponse.model_validate(replay)
        if existing_request.status in {
            GatewayRequestStatus.PENDING.value,
            GatewayRequestStatus.IN_FLIGHT.value,
            GatewayRequestStatus.RECONCILING.value,
            GatewayRequestStatus.UNKNOWN_PROVIDER_STATE.value,
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "request_id": payload.request_id,
                    "error_code": "REQUEST_ALREADY_IN_PROGRESS",
                    "message": "Request is already in progress.",
                    "retryable": True,
                },
            )

    provider = db.scalar(select(Provider).where(Provider.code == payload.provider_code, Provider.status == "ACTIVE"))
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    model = db.scalar(
        select(Model).where(
            Model.provider_id == provider.id,
            Model.model_code == payload.model_code,
            Model.status == "ACTIVE",
        )
    )
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")

    api_key = db.scalar(
        select(ApiKey)
        .where(
            ApiKey.provider_id == provider.id,
            ApiKey.department_id == current_user.department_id,
            ApiKey.status == "ACTIVE",
        )
        .order_by(ApiKey.is_primary.desc(), ApiKey.id.asc())
    )
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "request_id": payload.request_id,
                "error_code": "NO_ACTIVE_API_KEY",
                "message": "No active API key available for this department/provider.",
                "retryable": False,
            },
        )

    entitlement_result = evaluate_api_key_entitlement(
        db,
        api_key_id=int(api_key.id),
        user_id=int(current_user.id),
        department_id=int(current_user.department_id),
        project_id=payload.project_id,
        model_code=model.model_code,
    )
    if not entitlement_result.allowed:
        entitlement_error = (
            ENTITLEMENT_MODEL_NOT_ALLOWED
            if entitlement_result.reason == "MODEL_NOT_ALLOWED"
            else ENTITLEMENT_DENIED
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "request_id": payload.request_id,
                "error_code": entitlement_error.code,
                "message": entitlement_error.message,
                "retryable": entitlement_error.retryable,
                "policy_reason": entitlement_result.reason,
                "matched_subjects": entitlement_result.matched_subjects,
                "allowed_models": entitlement_result.constrained_models,
            },
        )

    trace_id = security_manager.generate_trace_id()
    gateway_request = existing_request
    if gateway_request is None:
        inserted_gateway_request_id = db.scalar(
            pg_insert(GatewayRequest)
            .values(
                request_id=payload.request_id,
                idempotency_key=payload.idempotency_key,
                trace_id=trace_id,
                user_id=current_user.id,
                department_id=current_user.department_id,
                project_id=payload.project_id,
                provider_id=provider.id,
                model_id=model.id,
                status=GatewayRequestStatus.PENDING.value,
            )
            .on_conflict_do_nothing()
            .returning(GatewayRequest.id)
        )
        if inserted_gateway_request_id is not None:
            gateway_request = db.get(GatewayRequest, inserted_gateway_request_id)
        else:
            gateway_request = db.scalar(
                select(GatewayRequest).where(
                    or_(
                        GatewayRequest.request_id == payload.request_id,
                        (GatewayRequest.idempotency_key == payload.idempotency_key)
                        & (GatewayRequest.user_id == current_user.id),
                    )
                )
            )
            if gateway_request is not None and gateway_request.status == GatewayRequestStatus.SUCCESS.value and gateway_request.raw_response_json:
                replay = dict(gateway_request.raw_response_json)
                replay["idempotent_replay"] = True
                return GatewayChatResponse.model_validate(replay)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "request_id": payload.request_id,
                    "error_code": "REQUEST_ALREADY_IN_PROGRESS",
                    "message": "Request is already in progress.",
                    "retryable": True,
                },
            )

    if gateway_request is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "request_id": payload.request_id,
                "error_code": "REQUEST_ALREADY_IN_PROGRESS",
                "message": "Request is already in progress.",
                "retryable": True,
            },
        )

    gateway_request.status = GatewayRequestStatus.IN_FLIGHT.value
    gateway_request.started_at = datetime.now(UTC)
    db.flush()

    active_price = get_active_model_price(db, model.id)
    if active_price is None:
        gateway_request.status = GatewayRequestStatus.FAILED_FINAL.value
        gateway_request.error_code = MODEL_PRICE_NOT_FOUND.code
        gateway_request.finished_at = datetime.now(UTC)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "request_id": payload.request_id,
                "error_code": MODEL_PRICE_NOT_FOUND.code,
                "message": MODEL_PRICE_NOT_FOUND.message,
                "retryable": MODEL_PRICE_NOT_FOUND.retryable,
            },
        )

    estimated_input_tokens, estimated_output_tokens = estimate_tokens_from_text(payload.message)
    estimated_cost = calculate_estimated_cost(
        input_tokens=estimated_input_tokens,
        output_tokens=estimated_output_tokens,
        input_price_per_1m=active_price.input_price_per_1m,
        output_price_per_1m=active_price.output_price_per_1m,
    )

    budget_check = evaluate_budget(
        db,
        user_id=current_user.id,
        department_id=current_user.department_id,
        project_id=payload.project_id,
        api_key_id=api_key.id,
        estimated_cost=estimated_cost,
    )

    if not budget_check.allowed:
        gateway_request.status = GatewayRequestStatus.FAILED_FINAL.value
        gateway_request.error_code = BUDGET_HARD_LIMIT_EXCEEDED.code
        gateway_request.finished_at = datetime.now(UTC)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "request_id": payload.request_id,
                "error_code": BUDGET_HARD_LIMIT_EXCEEDED.code,
                "message": BUDGET_HARD_LIMIT_EXCEEDED.message,
                "retryable": BUDGET_HARD_LIMIT_EXCEEDED.retryable,
            },
        )

    create_reservation(
        db,
        request_id=payload.request_id,
        user_id=current_user.id,
        department_id=current_user.department_id,
        project_id=payload.project_id,
        estimated_cost=estimated_cost,
        currency="USD",
    )
    db.flush()

    limit_result = check_rpm_limit(scope_key=f"{current_user.id}:{provider.code}:{model.model_code}", rpm_limit=120)
    if not limit_result.allowed:
        release_reservation(db, payload.request_id)
        gateway_request.status = GatewayRequestStatus.FAILED_RETRYABLE.value
        gateway_request.error_code = RATE_LIMIT_EXCEEDED.code
        gateway_request.finished_at = datetime.now(UTC)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "request_id": payload.request_id,
                "error_code": RATE_LIMIT_EXCEEDED.code,
                "message": RATE_LIMIT_EXCEEDED.message,
                "retryable": RATE_LIMIT_EXCEEDED.retryable,
            },
        )

    plain_api_key = security_manager.envelope_decrypt_api_key(api_key.encrypted_secret, api_key.encrypted_dek)

    try:
        provider_result = await provider_client.call_model(
            provider_base_url=provider.base_url,
            model_code=model.model_code,
            api_key=plain_api_key,
            message=payload.message,
        )
    except ProviderCallError as exc:
        now = datetime.now(UTC)
        gateway_request.provider_http_status = exc.provider_status
        gateway_request.finished_at = now

        if exc.retryable:
            if exc.provider_status is None:
                gateway_request.status = GatewayRequestStatus.UNKNOWN_PROVIDER_STATE.value
                gateway_request.error_code = "PROVIDER_TIMEOUT"
                mark_pending_reconciliation(db, payload.request_id)
            else:
                gateway_request.status = GatewayRequestStatus.FAILED_RETRYABLE.value
                gateway_request.error_code = "PROVIDER_RETRYABLE_ERROR"
                release_reservation(db, payload.request_id)
        else:
            gateway_request.status = GatewayRequestStatus.FAILED_FINAL.value
            gateway_request.error_code = "PROVIDER_NON_RETRYABLE_ERROR"
            release_reservation(db, payload.request_id)

        db.commit()

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "request_id": payload.request_id,
                "error_code": gateway_request.error_code,
                "message": str(exc),
                "retryable": exc.retryable,
            },
        ) from exc

    settled_cost = calculate_estimated_cost(
        input_tokens=provider_result.input_tokens,
        output_tokens=provider_result.output_tokens,
        input_price_per_1m=active_price.input_price_per_1m,
        output_price_per_1m=active_price.output_price_per_1m,
    )

    usage_event = db.scalar(
        select(UsageEvent).where(UsageEvent.request_id == payload.request_id).order_by(desc(UsageEvent.created_at))
    )
    if usage_event is None:
        inserted_usage_request_id = db.scalar(
            pg_insert(UsageEventRequestKey)
            .values(request_id=payload.request_id)
            .on_conflict_do_nothing(index_elements=[UsageEventRequestKey.request_id])
            .returning(UsageEventRequestKey.request_id)
        )

        if inserted_usage_request_id is None:
            usage_event = db.scalar(
                select(UsageEvent)
                .where(UsageEvent.request_id == payload.request_id)
                .order_by(desc(UsageEvent.created_at))
            )

        if usage_event is None:
            usage_event = UsageEvent(
                id=_next_usage_event_id(db),
                request_id=payload.request_id,
                idempotency_key=payload.idempotency_key,
                user_id=current_user.id,
                department_id=current_user.department_id,
                project_id=payload.project_id,
                provider_id=provider.id,
                model_id=model.id,
                api_key_id=api_key.id,
                price_version_id=active_price.id,
                request_type="CHAT",
                input_tokens=provider_result.input_tokens,
                output_tokens=provider_result.output_tokens,
                cached_input_tokens=0,
                reasoning_tokens=0,
                total_tokens=provider_result.total_tokens,
                estimated_cost_usd=settled_cost,
                latency_ms=provider_result.latency_ms,
                status="SUCCESS",
                error_code=None,
                prompt_hash=hashlib.sha256(payload.message.encode("utf-8")).hexdigest(),
                metadata_json={
                    **payload.metadata_json,
                    "trace_id": trace_id,
                    "provider_status": "SUCCESS",
                },
            )
            db.add(usage_event)
            db.flush()

    usage_event_id = usage_event.id
    if usage_event_id is None:
        usage_event_id = db.scalar(
            select(UsageEvent.id)
            .where(UsageEvent.request_id == payload.request_id)
            .order_by(desc(UsageEvent.created_at))
            .limit(1)
        )
    if usage_event_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "request_id": payload.request_id,
                "error_code": "USAGE_EVENT_ID_RESOLVE_FAILED",
                "message": "Failed to resolve usage event id after insert.",
                "retryable": False,
            },
        )

    ledger = db.scalar(
        select(CostLedger)
        .where(
            or_(
                CostLedger.request_id == payload.request_id,
                (CostLedger.idempotency_key == payload.idempotency_key) & (CostLedger.user_id == current_user.id),
            )
        )
        .order_by(desc(CostLedger.id))
    )
    if ledger is None:
        ledger = CostLedger(
            request_id=payload.request_id,
            idempotency_key=payload.idempotency_key,
            usage_event_id=usage_event_id,
            user_id=current_user.id,
            department_id=current_user.department_id,
            project_id=payload.project_id,
            provider_id=provider.id,
            model_id=model.id,
            price_version_id=active_price.id,
            currency=active_price.currency,
            input_tokens=provider_result.input_tokens,
            output_tokens=provider_result.output_tokens,
            input_unit_price=active_price.input_price_per_1m,
            output_unit_price=active_price.output_price_per_1m,
            estimated_cost=estimated_cost,
            settled_cost=settled_cost,
            ledger_type=LedgerType.CHARGE.value,
        )
        db.add(ledger)
        db.flush()

    settle_reservation(db, payload.request_id, settled_amount=settled_cost)
    recompute_limit_state(db, api_key_id=api_key.id, updated_by_user_id=current_user.id)

    remaining_budget = max(Decimal("0"), budget_check.remaining_budget - settled_cost)

    response_data = GatewayChatResponse(
        request_id=payload.request_id,
        provider=provider.code,
        model=model.model_code,
        answer=provider_result.answer,
        usage=UsageInfo(
            input_tokens=provider_result.input_tokens,
            output_tokens=provider_result.output_tokens,
            total_tokens=provider_result.total_tokens,
            estimated_cost_usd=settled_cost,
        ),
        remaining_budget_usd=remaining_budget,
        idempotent_replay=False,
    )

    gateway_request.status = GatewayRequestStatus.SUCCESS.value
    gateway_request.provider_http_status = 200
    gateway_request.error_code = None
    gateway_request.finished_at = datetime.now(UTC)
    gateway_request.raw_response_json = response_data.model_dump(mode="json")

    write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="GATEWAY_CHAT",
        resource_type="gateway_requests",
        resource_id=str(gateway_request.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={
            "request_id": payload.request_id,
            "provider": provider.code,
            "model": model.model_code,
            "cost": str(settled_cost),
            "total_tokens": provider_result.total_tokens,
            "price_version_id": active_price.id,
        },
        metadata_json={"trace_id": trace_id},
    )

    db.commit()
    return response_data
