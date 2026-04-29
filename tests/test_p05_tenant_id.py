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


class TestTenantIdMigrationFreshDatabase:
    """Fresh Alembic upgrade must not assume the incidents table already exists."""

    def test_0004_creates_incidents_before_adding_tenant_indexes(self, monkeypatch) -> None:
        import importlib.util
        from pathlib import Path

        migration_path = Path("alembic/versions/0004_tenant_id_columns.py")
        spec = importlib.util.spec_from_file_location("bsupervisor_0004_migration", migration_path)
        assert spec is not None and spec.loader is not None
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        operations: list[object] = []

        class FakeOp:
            def get_bind(self):
                return object()

            def create_table(self, *args, **kwargs):
                operations.append(("create_table", args[0]))

            def create_index(self, *args, **kwargs):
                operations.append(("create_index", args[0], args[1]))

            def add_column(self, table_name, column):
                operations.append(("add_column", table_name, column.name))

        class FakeInspector:
            def get_table_names(self):
                return ["audit_events", "audit_rules", "cost_records", "daily_reports"]

            def get_columns(self, table):
                return []

        monkeypatch.setattr(migration, "op", FakeOp())
        monkeypatch.setattr(migration, "inspect", lambda _bind: FakeInspector())

        migration.upgrade()

        assert ("create_table", "incidents") in operations
        assert ("add_column", "audit_events", "tenant_id") in operations


class TestAuditEventJsonColumnMigration:
    """Model columns used by the events API must be present after Alembic upgrade."""

    def test_audit_event_json_columns_exist_on_model(self) -> None:
        assert _has_column(AuditEvent, "explanation_json")
        assert _has_column(AuditEvent, "feedback_json")

    def test_0006_adds_explanation_and_feedback_columns(self, monkeypatch) -> None:
        import importlib.util
        from pathlib import Path

        migration_path = Path("alembic/versions/0006_audit_event_explanation_feedback.py")
        spec = importlib.util.spec_from_file_location("bsupervisor_0006_migration", migration_path)
        assert spec is not None and spec.loader is not None
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        operations: list[tuple[str, str, str]] = []

        class FakeOp:
            def add_column(self, table_name, column):
                operations.append(("add_column", table_name, column.name))

            def drop_column(self, table_name, column_name):
                operations.append(("drop_column", table_name, column_name))

        monkeypatch.setattr(migration, "op", FakeOp())

        migration.upgrade()

        assert ("add_column", "audit_events", "explanation_json") in operations
        assert ("add_column", "audit_events", "feedback_json") in operations
