# File Path: backend/alembic/versions/d8f1a37c4b2e_gateway_idempotency_hardening.py
# Timestamp: 2026-05-26T22:30:00+08:00
# Version: v0.1

"""gateway idempotency hardening

Revision ID: d8f1a37c4b2e
Revises: 9c2b4d1a7f88
Create Date: 2026-05-26 22:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8f1a37c4b2e"
down_revision: Union[str, None] = "9c2b4d1a7f88"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usage_event_request_keys",
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("request_id"),
    )

    op.execute(
        """
        INSERT INTO usage_event_request_keys (request_id, created_at)
        SELECT request_id, MIN(created_at)
        FROM usage_events
        GROUP BY request_id
        ON CONFLICT (request_id) DO NOTHING
        """
    )

    op.add_column("cost_ledger", sa.Column("idempotency_key", sa.String(length=80), nullable=True))

    op.execute(
        """
        UPDATE cost_ledger AS cl
        SET idempotency_key = COALESCE(gr.idempotency_key, cl.request_id)
        FROM gateway_requests AS gr
        WHERE gr.request_id = cl.request_id
          AND cl.idempotency_key IS NULL
        """
    )
    op.execute("UPDATE cost_ledger SET idempotency_key = request_id WHERE idempotency_key IS NULL")

    op.alter_column(
        "cost_ledger",
        "idempotency_key",
        existing_type=sa.String(length=80),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_cost_ledger_idempotency_user",
        "cost_ledger",
        ["idempotency_key", "user_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_cost_ledger_idempotency_user", "cost_ledger", type_="unique")
    op.drop_column("cost_ledger", "idempotency_key")
    op.drop_table("usage_event_request_keys")
