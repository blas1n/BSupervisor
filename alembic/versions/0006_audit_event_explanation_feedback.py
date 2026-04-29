"""Add explainable-block and feedback JSON columns to audit_events.

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "audit_events",
        sa.Column("explanation_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("feedback_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("audit_events", "feedback_json")
    op.drop_column("audit_events", "explanation_json")
