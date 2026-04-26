"""Phase 0 P0.5 — tenant_id column on every tenant-scoped table.

BSupervisor was originally single-tenant. Phase 0 introduces the
``tenants`` / ``tenant_members`` tables in BSVibe-Auth (PR #3), and every
product table that holds user-visible data must carry a ``tenant_id``
foreign-key-by-convention column so cross-tenant leakage is impossible.

Lockin §3 decision #11 — every product table has tenant_id. DDL only;
no backfill (no production data exists yet).
"""

from __future__ import annotations

from sqlalchemy import inspect

from bsupervisor.models import (
    AuditEvent,
    AuditRule,
    CostRecord,
    DailyReport,
    Incident,
)


def _has_column(model: type, column_name: str) -> bool:
    return column_name in inspect(model).columns.keys()


class TestTenantIdColumnsExist:
    """Every tenant-scoped table MUST have a ``tenant_id`` column."""

    def test_audit_events_has_tenant_id(self) -> None:
        assert _has_column(AuditEvent, "tenant_id")

    def test_audit_rules_has_tenant_id(self) -> None:
        assert _has_column(AuditRule, "tenant_id")

    def test_cost_records_has_tenant_id(self) -> None:
        assert _has_column(CostRecord, "tenant_id")

    def test_daily_reports_has_tenant_id(self) -> None:
        assert _has_column(DailyReport, "tenant_id")

    def test_incidents_has_tenant_id(self) -> None:
        assert _has_column(Incident, "tenant_id")


class TestTenantIdColumnShape:
    """``tenant_id`` is a String(255) column, indexed, nullable=True (Phase 0).

    Phase 0.4-후속 will tighten this to ``nullable=False`` after backfill.
    """

    def test_audit_events_tenant_id_indexed(self) -> None:
        cols = inspect(AuditEvent).columns
        assert cols["tenant_id"].index or any(
            "tenant_id" in idx.columns.keys() for idx in inspect(AuditEvent).tables[0].indexes
        )

    def test_cost_records_tenant_id_indexed(self) -> None:
        cols = inspect(CostRecord).columns
        assert cols["tenant_id"].index or any(
            "tenant_id" in idx.columns.keys() for idx in inspect(CostRecord).tables[0].indexes
        )
