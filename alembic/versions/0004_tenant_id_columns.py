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
from sqlalchemy import inspect

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
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "incidents" not in existing_tables:
        op.create_table(
            "incidents",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("agent_id", sa.String(255), nullable=False, index=True),
            sa.Column("title", sa.String(1024), nullable=False),
            sa.Column("status", sa.String(50), nullable=False),
            sa.Column("severity", sa.String(50), nullable=False),
            sa.Column("event_count", sa.Integer(), nullable=False),
            sa.Column(
                "started_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("tenant_id", sa.String(length=255), nullable=True),
        )
        op.create_index("ix_incidents_tenant_id", "incidents", ["tenant_id"])
        existing_tables.add("incidents")

    for table in _TABLES:
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "tenant_id" in columns:
            continue
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
