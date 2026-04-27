"""Phase Audit Batch 2 — ``audit_outbox`` table for bsvibe-audit relay.

Mirrors :class:`bsvibe_audit.AuditOutboxRecord`. Same schema lives in the
other three BSVibe products (BSGateway / BSNexus / BSage); rendering the
DDL here keeps Alembic the single source of truth for BSupervisor's
production database.

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_outbox",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dead_letter", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_audit_outbox_undelivered",
        "audit_outbox",
        ["delivered_at", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_outbox_undelivered", table_name="audit_outbox")
    op.drop_table("audit_outbox")
