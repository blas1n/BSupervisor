"""Initial schema — audit_events, audit_rules, cost_records, daily_reports.

Revision ID: 0001
Revises:
Create Date: 2026-03-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_id", sa.String(255), nullable=False, index=True),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(255), nullable=False, index=True),
        sa.Column("action", sa.String(255), nullable=False),
        sa.Column("target", sa.String(1024), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("allowed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "audit_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("condition", sa.JSON(), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("built_in", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.create_table(
        "cost_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_id", sa.String(255), nullable=False, index=True),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False),
        sa.Column("tokens_out", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "daily_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False, unique=True, index=True),
        sa.Column("total_events", sa.Integer(), nullable=False),
        sa.Column("blocked_count", sa.Integer(), nullable=False),
        sa.Column("total_cost_usd", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("report_json", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("daily_reports")
    op.drop_table("cost_records")
    op.drop_table("audit_rules")
    op.drop_table("audit_events")
