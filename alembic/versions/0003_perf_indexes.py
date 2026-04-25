"""Audit §M6 — composite + timestamp indexes for hot range scans.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Cost queries: GET /api/costs (totals + 30-day GROUP BY trend), per-agent
    # daily aggregation in ``CostTracker.get_daily_cost``.
    op.create_index(
        "ix_cost_records_agent_id_timestamp",
        "cost_records",
        ["agent_id", "timestamp"],
    )
    op.create_index(
        "ix_cost_records_timestamp",
        "cost_records",
        ["timestamp"],
    )

    # Event queries: status/reporter daily windows, IncidentTracker timeline.
    op.create_index(
        "ix_audit_events_agent_id_timestamp",
        "audit_events",
        ["agent_id", "timestamp"],
    )
    op.create_index(
        "ix_audit_events_timestamp",
        "audit_events",
        ["timestamp"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_timestamp", table_name="audit_events")
    op.drop_index("ix_audit_events_agent_id_timestamp", table_name="audit_events")
    op.drop_index("ix_cost_records_timestamp", table_name="cost_records")
    op.drop_index("ix_cost_records_agent_id_timestamp", table_name="cost_records")
