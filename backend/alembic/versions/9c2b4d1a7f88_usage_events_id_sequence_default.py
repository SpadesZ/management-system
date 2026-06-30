# File Path: backend/alembic/versions/9c2b4d1a7f88_usage_events_id_sequence_default.py
# Timestamp: 2026-05-26T22:10:00+08:00
# Version: v0.1

"""usage events id sequence default

Revision ID: 9c2b4d1a7f88
Revises: 81d9497289c9
Create Date: 2026-05-26 22:10:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c2b4d1a7f88"
down_revision: Union[str, None] = "81d9497289c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS usage_events_id_seq")
    op.execute("ALTER TABLE usage_events ALTER COLUMN id SET DEFAULT nextval('usage_events_id_seq')")
    op.execute("ALTER SEQUENCE usage_events_id_seq OWNED BY usage_events.id")
    op.execute(
        """
        SELECT setval(
            'usage_events_id_seq',
            COALESCE((SELECT MAX(id) FROM usage_events), 0) + 1,
            false
        )
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE usage_events ALTER COLUMN id DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS usage_events_id_seq")
