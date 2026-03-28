"""Tests for POST /api/events endpoint."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from bsupervisor.models import AuditEvent


@pytest.fixture
def valid_event_payload():
    return {
        "agent_id": "agent-001",
        "source": "bsnexus",
        "event_type": "file_access",
        "action": "read",
        "target": "/data/report.csv",
        "metadata": {"user": "alice"},
        "timestamp": "2026-03-28T10:00:00Z",
    }


async def test_ingest_valid_event(client, db_session, valid_event_payload):
    response = await client.post("/api/events", json=valid_event_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["allowed"] is True
    assert "event_id" in data


async def test_ingest_event_without_optional_fields(client, db_session):
    payload = {
        "agent_id": "agent-002",
        "source": "cli",
        "event_type": "shell_exec",
        "action": "execute",
        "target": "ls -la",
    }
    response = await client.post("/api/events", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["allowed"] is True
    assert "event_id" in data


async def test_ingest_event_missing_required_field(client, db_session):
    payload = {
        "agent_id": "agent-001",
        # missing source, event_type, action, target
    }
    response = await client.post("/api/events", json=payload)

    assert response.status_code == 422


async def test_ingest_event_stores_in_db(client, db_session, valid_event_payload):
    response = await client.post("/api/events", json=valid_event_payload)

    assert response.status_code == 200
    event_id = response.json()["event_id"]

    result = await db_session.execute(select(AuditEvent).where(AuditEvent.id == uuid.UUID(event_id)))
    event = result.scalar_one()

    assert event.agent_id == "agent-001"
    assert event.source == "bsnexus"
    assert event.event_type == "file_access"
    assert event.action == "read"
    assert event.target == "/data/report.csv"
    assert event.metadata_json == {"user": "alice"}
    assert event.allowed is True


async def test_ingest_event_stores_timestamp(client, db_session, valid_event_payload):
    response = await client.post("/api/events", json=valid_event_payload)

    assert response.status_code == 200
    event_id = response.json()["event_id"]

    result = await db_session.execute(select(AuditEvent).where(AuditEvent.id == uuid.UUID(event_id)))
    event = result.scalar_one()

    assert event.timestamp is not None


async def test_ingest_event_auto_timestamp_when_omitted(client, db_session):
    payload = {
        "agent_id": "agent-003",
        "source": "api",
        "event_type": "data_access",
        "action": "query",
        "target": "users_table",
    }
    response = await client.post("/api/events", json=payload)

    assert response.status_code == 200
    event_id = response.json()["event_id"]

    result = await db_session.execute(select(AuditEvent).where(AuditEvent.id == uuid.UUID(event_id)))
    event = result.scalar_one()
    assert event.timestamp is not None
