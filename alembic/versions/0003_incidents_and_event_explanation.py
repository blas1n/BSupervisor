"""Add incidents table and event explanation/feedback columns.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Event explanation & feedback columns
    op.add_column("audit_events", sa.Column("explanation_json", sa.JSON(), nullable=True))
    op.add_column("audit_events", sa.Column("feedback_json", sa.JSON(), nullable=True))

    # Incidents table
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="open"),
        sa.Column("severity", sa.String(50), nullable=False, server_default="medium"),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_incidents_agent_id", "incidents", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_incidents_agent_id", table_name="incidents")
    op.drop_table("incidents")
    op.drop_column("audit_events", "feedback_json")
    op.drop_column("audit_events", "explanation_json")
