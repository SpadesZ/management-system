# File Path: backend/app/services/pricing.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.entities import ModelPrice


def get_active_model_price(db: Session, model_id: int, at_time: datetime | None = None) -> ModelPrice | None:
    target_time = at_time or datetime.now(UTC)
    stmt = (
        select(ModelPrice)
        .where(
            ModelPrice.model_id == model_id,
            ModelPrice.effective_from <= target_time,
            or_(ModelPrice.effective_to.is_(None), ModelPrice.effective_to > target_time),
        )
        .order_by(ModelPrice.effective_from.desc())
    )
    return db.scalar(stmt)


def validate_model_price_no_overlap(
    db: Session,
    *,
    model_id: int,
    effective_from: datetime,
    effective_to: datetime | None,
) -> bool:
    overlap_conditions = [
        ModelPrice.model_id == model_id,
        or_(ModelPrice.effective_to.is_(None), ModelPrice.effective_to > effective_from),
    ]
    if effective_to is not None:
        overlap_conditions.append(ModelPrice.effective_from < effective_to)

    overlap_stmt = select(ModelPrice.id).where(and_(*overlap_conditions))
    exists_id = db.scalar(overlap_stmt)
    return exists_id is None


def calculate_estimated_cost(
    *,
    input_tokens: int,
    output_tokens: int,
    input_price_per_1m: Decimal,
    output_price_per_1m: Decimal,
) -> Decimal:
    input_cost = (Decimal(input_tokens) / Decimal(1_000_000)) * input_price_per_1m
    output_cost = (Decimal(output_tokens) / Decimal(1_000_000)) * output_price_per_1m
    return (input_cost + output_cost).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def estimate_tokens_from_text(message: str) -> tuple[int, int]:
    chars = len(message)
    estimated_input_tokens = max(1, chars // 4)
    estimated_output_tokens = max(16, estimated_input_tokens // 3)
    return estimated_input_tokens, estimated_output_tokens
