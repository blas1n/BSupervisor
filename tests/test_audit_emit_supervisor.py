"""Phase Audit Batch 2 — supervisor.* domain event emission tests.

Verifies that the four supervisor.* events documented in
:mod:`bsvibe_audit.events.supervisor` end up in the local
``audit_outbox`` table at the right code points:

* ``supervisor.rule.violated``  — rule engine match (block or warn).
* ``supervisor.budget.exceeded`` — daily cost threshold crossed.
* ``supervisor.alert.published`` — rate-limit / incident creation.
* ``supervisor.anomaly.detected`` — anomaly detector firing.

Hybrid emit strategy (Audit-3): the ``rule.violated`` path is decorated
via ``@audit_emit`` because the kwargs already carry actor/session, the
other three are manual ``emitter.emit(event, session=db)`` calls because
they live deep inside the request path or background tasks where the
auto-decorator can't pull the right kwargs.

These tests pin the producer-side contract; relay/transport semantics
are owned by ``bsvibe-audit`` itself and tested upstream.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from bsupervisor.models.audit_event import AuditEvent
from bsupervisor.models.audit_rule import AuditRule
from bsupervisor.models.cost_record import CostRecord


def _outbox_table():
    """Return the SQLAlchemy ``audit_outbox`` Table object.

    Imported lazily so the test file doesn't require the audit package at
    collection time; if the producer is not wired up yet the import will
    surface the failure at the first test that needs it.
    """
    from bsvibe_audit.outbox.schema import AuditOutboxRecord

    return AuditOutboxRecord


async def _fetch_outbox_events(db_session, *, event_type: str | None = None) -> list[dict]:
    record = _outbox_table()
    stmt = select(record).order_by(record.id.asc())
    if event_type is not None:
        stmt = stmt.where(record.event_type == event_type)
    result = await db_session.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "event_type": row.event_type,
            "event_id": row.event_id,
            "payload": row.payload,
            "occurred_at": row.occurred_at,
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# supervisor.rule.violated
# ---------------------------------------------------------------------------


@pytest.fixture
def rule_block_payload():
    """Event payload that is guaranteed to hit a built-in block rule."""

    return {
        "agent_id": "agent-rule-1",
        "source": "bsnexus",
        "event_type": "file_delete",
        "action": "delete",
        "target": "/etc/secrets/.env",  # ends in .env -> block
    }


@pytest.fixture
def rule_warn_payload():
    """Event payload that triggers a warn-level rule (no block)."""

    return {
        "agent_id": "agent-rule-2",
        "source": "bsnexus",
        "event_type": "file_access",
        "action": "read",
        "target": "/data/report.csv",
    }


async def test_block_rule_emits_rule_violated_event(client, db_session, rule_block_payload):
    response = await client.post("/api/events", json=rule_block_payload)
    assert response.status_code == 201
    body = response.json()
    assert body["allowed"] is False

    rows = await _fetch_outbox_events(db_session, event_type="supervisor.rule.violated")
    assert len(rows) == 1
    payload = rows[0]["payload"]
    assert payload["actor"]["type"] in {"service", "user", "system"}
    # The agent_id MUST appear inside ``data`` so consumers can correlate.
    assert payload["data"]["agent_id"] == "agent-rule-1"
    # Severity comes from the explanation block.
    assert payload["data"]["action_taken"] == "block"
    assert payload["data"]["rule_name"].startswith("builtin:")


async def test_allowed_event_does_not_emit_rule_violated(client, db_session):
    payload = {
        "agent_id": "agent-allowed",
        "source": "bsnexus",
        "event_type": "file_access",
        "action": "read",
        "target": "/data/clean.csv",
    }
    response = await client.post("/api/events", json=payload)
    assert response.status_code == 201

    rows = await _fetch_outbox_events(db_session, event_type="supervisor.rule.violated")
    assert rows == []


async def test_warn_rule_emits_rule_violated_event(client, db_session, rule_warn_payload):
    # Pre-seed a custom warn rule so the engine returns a non-None rule_name
    # without blocking the event.
    db_session.add(
        AuditRule(
            id=uuid.uuid4(),
            name="warn-on-csv-read",
            description="Warn when an agent reads CSVs",
            condition={"event_type": "file_access", "severity": "low"},
            action="warn",
            enabled=True,
        ),
    )
    await db_session.commit()

    response = await client.post("/api/events", json=rule_warn_payload)
    assert response.status_code == 201
    body = response.json()
    assert body["allowed"] is True

    rows = await _fetch_outbox_events(db_session, event_type="supervisor.rule.violated")
    assert len(rows) == 1
    assert rows[0]["payload"]["data"]["action_taken"] == "warn"
    assert rows[0]["payload"]["data"]["rule_name"] == "warn-on-csv-read"


# ---------------------------------------------------------------------------
# supervisor.budget.exceeded
# ---------------------------------------------------------------------------


async def test_budget_exceeded_emits_event(client, db_session):
    """When today's cost crosses the daily threshold, emit budget.exceeded."""
    from bsupervisor.config import settings as app_settings

    threshold = app_settings.daily_cost_threshold_usd
    # Pre-seed today's cost RIGHT at the threshold so the next event's
    # cost-threshold check fires.
    db_session.add(
        CostRecord(
            agent_id="agent-budget",
            model="claude-3.5",
            tokens_in=1000,
            tokens_out=1000,
            cost_usd=Decimal(threshold) + Decimal("1"),
            timestamp=datetime.now(tz=timezone.utc),
        ),
    )
    await db_session.commit()

    response = await client.post(
        "/api/events",
        json={
            "agent_id": "agent-budget",
            "source": "bsnexus",
            "event_type": "file_access",
            "action": "read",
            "target": "/data/clean.csv",
        },
    )
    assert response.status_code == 201

    rows = await _fetch_outbox_events(db_session, event_type="supervisor.budget.exceeded")
    assert len(rows) == 1
    payload = rows[0]["payload"]
    assert payload["data"]["agent_id"] == "agent-budget"
    # ``current_cost_usd`` and ``threshold_usd`` MUST be on the wire so
    # downstream consumers know what triggered this.
    assert "current_cost_usd" in payload["data"]
    assert "threshold_usd" in payload["data"]


async def test_budget_under_threshold_does_not_emit(client, db_session):
    """No emit when daily cost is well below the threshold."""

    response = await client.post(
        "/api/events",
        json={
            "agent_id": "agent-quiet",
            "source": "bsnexus",
            "event_type": "file_access",
            "action": "read",
            "target": "/data/quiet.csv",
        },
    )
    assert response.status_code == 201

    rows = await _fetch_outbox_events(db_session, event_type="supervisor.budget.exceeded")
    assert rows == []


# ---------------------------------------------------------------------------
# supervisor.alert.published
# ---------------------------------------------------------------------------


async def test_rate_limit_emits_alert_published(client, db_session, monkeypatch):
    """A 429 from the rate limiter publishes an alert event."""
    import bsupervisor.api.events as events_mod
    from bsupervisor.core.rate_limiter import InMemoryRateLimiter

    # Replace the module limiter with one that always says no.
    monkeypatch.setattr(events_mod, "_events_rate_limiter", InMemoryRateLimiter(max_requests=0, window_seconds=60.0))

    response = await client.post(
        "/api/events",
        json={
            "agent_id": "agent-rl",
            "source": "noisy-source",
            "event_type": "file_access",
            "action": "read",
            "target": "/data/x",
        },
    )
    assert response.status_code == 429

    rows = await _fetch_outbox_events(db_session, event_type="supervisor.alert.published")
    assert len(rows) == 1
    assert rows[0]["payload"]["data"]["alert_type"] == "rate_limit_exceeded"
    assert rows[0]["payload"]["data"]["source"] == "noisy-source"


async def test_incident_creation_emits_alert_published(client, db_session, rule_block_payload):
    """Creating a new incident from a blocked event publishes an alert."""

    response = await client.post("/api/events", json=rule_block_payload)
    assert response.status_code == 201

    rows = await _fetch_outbox_events(db_session, event_type="supervisor.alert.published")
    # Only the *new* incident should fire — existing-incident merges should not.
    assert len(rows) == 1
    payload = rows[0]["payload"]
    assert payload["data"]["alert_type"] == "incident_created"
    assert payload["resource"]["type"] == "incident"
    assert payload["data"]["agent_id"] == "agent-rule-1"


# ---------------------------------------------------------------------------
# supervisor.anomaly.detected
# ---------------------------------------------------------------------------


async def test_anomaly_endpoint_emits_anomaly_detected(client, db_session):
    """When ``GET /api/anomalies`` returns >=1 anomaly, emit per-anomaly events."""
    now = datetime.now(tz=timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Seed 3 quiet history days @ $1/day and a today spike of $1000.
    for offset in (1, 2, 3):
        db_session.add(
            CostRecord(
                agent_id="anom-agent",
                model="claude",
                tokens_in=1,
                tokens_out=1,
                cost_usd=Decimal("1.00"),
                timestamp=today_start - timedelta(days=offset, hours=1),
            ),
        )
    db_session.add(
        CostRecord(
            agent_id="anom-agent",
            model="claude",
            tokens_in=1,
            tokens_out=1,
            cost_usd=Decimal("1000.00"),
            timestamp=today_start + timedelta(hours=1),
        ),
    )
    await db_session.commit()

    response = await client.get("/api/anomalies")
    assert response.status_code == 200
    body = response.json()
    assert any(item["agent_id"] == "anom-agent" for item in body)

    rows = await _fetch_outbox_events(db_session, event_type="supervisor.anomaly.detected")
    assert len(rows) >= 1
    payload = rows[0]["payload"]
    assert payload["data"]["agent_id"] == "anom-agent"
    assert payload["data"]["metric"] in {"cost", "event_count"}


async def test_no_anomaly_no_emit(client, db_session):
    """Empty anomaly result emits nothing."""
    response = await client.get("/api/anomalies")
    assert response.status_code == 200
    rows = await _fetch_outbox_events(db_session, event_type="supervisor.anomaly.detected")
    assert rows == []


# ---------------------------------------------------------------------------
# Domain regression: emit failure must NOT break the request
# ---------------------------------------------------------------------------


async def test_emit_failure_does_not_break_event_ingest(
    client,
    db_session,
    rule_block_payload,
    monkeypatch,
):
    """If audit emit raises, the API still returns 201 and persists the event.

    sync API contract: domain writes MUST succeed even if audit infra is
    down. The producer-side ``safe_emit`` wraps every supervisor.* call.
    """
    from bsupervisor.core import audit as audit_mod

    async def _boom(event, session):
        raise RuntimeError("simulated audit failure")

    monkeypatch.setattr(audit_mod._supervisor_emitter, "emit", _boom)

    response = await client.post("/api/events", json=rule_block_payload)
    assert response.status_code == 201

    # Domain row still persisted.
    result = await db_session.execute(select(AuditEvent))
    events = list(result.scalars().all())
    assert len(events) == 1
    assert events[0].allowed is False
