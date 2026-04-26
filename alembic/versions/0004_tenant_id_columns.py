"""P0.5 — add tenant_id column + index to every tenant-scoped table.

Lockin §3 decision #11. DDL only (no backfill — no production data).
Phase 0.4-후속 will tighten ``tenant_id`` to ``nullable=False`` after
backfill from BSGateway / BSNexus.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLES: tuple[str, ...] = (
    "audit_events",
    "audit_rules",
    "cost_records",
    "daily_reports",
    "incidents",
)


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("tenant_id", sa.String(length=255), nullable=True),
        )
        op.create_index(
            f"ix_{table}_tenant_id",
            table,
            ["tenant_id"],
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_column(table, "tenant_id")
