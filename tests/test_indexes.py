"""Index coverage — Audit §M6 (and the related ``timestamp`` scans).

The audit calls out the missing ``(agent_id, timestamp)`` composite on
``cost_records`` (used by ``CostTracker.get_daily_cost`` and the per-agent
breakdown in ``GET /api/costs``). The same pattern applies to
``audit_events`` for the status / reporter / incident-tracker queries that
filter ``WHERE timestamp BETWEEN start AND end`` and frequently
``AND agent_id = :id``.

These tests use SQLAlchemy's metadata to verify the indexes are declared
on the ORM models — independent of which migration created them — so they
catch a regression where a model refactor drops the index.
"""

from sqlalchemy import Index

from bsupervisor.models.audit_event import AuditEvent
from bsupervisor.models.cost_record import CostRecord


def _index_columns(table) -> set[tuple[str, ...]]:
    cols: set[tuple[str, ...]] = set()
    for ix in table.indexes:
        if isinstance(ix, Index):
            cols.add(tuple(c.name for c in ix.columns))
    # Single-column inline indexes (``index=True``) appear as ix_<table>_<col>.
    for col in table.columns:
        if col.index:
            cols.add((col.name,))
    return cols


class TestCostRecordIndexes:
    def test_agent_id_timestamp_composite_index(self) -> None:
        """Audit §M6 — required for per-agent daily aggregation."""
        cols = _index_columns(CostRecord.__table__)
        assert ("agent_id", "timestamp") in cols, f"missing composite index (agent_id, timestamp) — have: {cols}"

    def test_timestamp_index_for_range_scans(self) -> None:
        """Used by GET /api/costs total/agent breakdown and reporter queries."""
        cols = _index_columns(CostRecord.__table__)
        assert any("timestamp" in c for c in cols), f"no index covers timestamp on cost_records — have: {cols}"


class TestAuditEventIndexes:
    def test_agent_id_timestamp_composite_index(self) -> None:
        """Used by IncidentTracker.list_events_in_window."""
        cols = _index_columns(AuditEvent.__table__)
        assert ("agent_id", "timestamp") in cols, f"missing composite index (agent_id, timestamp) — have: {cols}"

    def test_timestamp_index_for_range_scans(self) -> None:
        """Used by status/reporter daily windows."""
        cols = _index_columns(AuditEvent.__table__)
        assert any("timestamp" in c for c in cols), f"no index covers timestamp on audit_events — have: {cols}"
