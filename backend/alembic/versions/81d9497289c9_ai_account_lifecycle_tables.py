# File Path: backend/alembic/versions/81d9497289c9_ai_account_lifecycle_tables.py
# Timestamp: 2026-05-26T21:00:00+08:00
# Version: v0.1

"""ai account lifecycle tables

Revision ID: 81d9497289c9
Revises: 284216425e18
Create Date: 2026-05-26 19:51:28.219693

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "81d9497289c9"
down_revision: Union[str, None] = "284216425e18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_account_access_grants",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("ai_account_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("granted_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("grant_reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("revoked_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('ACTIVE','REVOKED')", name="ck_ai_account_access_grant_status"),
        sa.ForeignKeyConstraint(["ai_account_id"], ["ai_accounts.id"]),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_account_access_grants_account_status",
        "ai_account_access_grants",
        ["ai_account_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_account_access_grants_user_status",
        "ai_account_access_grants",
        ["user_id", "status"],
        unique=False,
    )

    op.create_table(
        "ai_account_credentials",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("ai_account_id", sa.BigInteger(), nullable=False),
        sa.Column("credential_name", sa.String(length=120), nullable=False),
        sa.Column("credential_type", sa.String(length=32), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("encrypted_dek", sa.Text(), nullable=False),
        sa.Column("kms_key_id", sa.String(length=128), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("masked_secret", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("credential_type IN ('PASSWORD','TOKEN','COOKIE','OTHER')", name="ck_ai_account_credential_type"),
        sa.CheckConstraint("status IN ('ACTIVE','DISABLED')", name="ck_ai_account_credential_status"),
        sa.ForeignKeyConstraint(["ai_account_id"], ["ai_accounts.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ai_account_id", "credential_name", name="uq_ai_account_credential_name"),
    )
    op.create_index(
        "ix_ai_account_credentials_account_status",
        "ai_account_credentials",
        ["ai_account_id", "status"],
        unique=False,
    )

    op.create_table(
        "ai_account_history",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("ai_account_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("event_time", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("detail_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["ai_account_id"], ["ai_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_account_history_account_event_time",
        "ai_account_history",
        ["ai_account_id", "event_time"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_account_history_account_event_time", table_name="ai_account_history")
    op.drop_table("ai_account_history")

    op.drop_index("ix_ai_account_credentials_account_status", table_name="ai_account_credentials")
    op.drop_table("ai_account_credentials")

    op.drop_index("ix_ai_account_access_grants_user_status", table_name="ai_account_access_grants")
    op.drop_index("ix_ai_account_access_grants_account_status", table_name="ai_account_access_grants")
    op.drop_table("ai_account_access_grants")
