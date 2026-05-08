"""Tests for the Incident Timeline feature.

Verifies that blocked events create incidents grouping related events
by agent within a time window, providing a forensic timeline view.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.core.incident_tracker import IncidentTracker
from bsupervisor.models.audit_event import AuditEvent
from bsupervisor.models.incident import Incident, IncidentStatus


def _make_event(
    session: AsyncSession,
    agent_id: str = "agent-1",
    event_type: str = "file_access",
    action: str = "read",
    target: str = "/tmp/data.txt",
    allowed: bool = True,
    timestamp: datetime | None = None,
) -> AuditEvent:
    event = AuditEvent(
        agent_id=agent_id,
        source="test",
        event_type=event_type,
        action=action,
        target=target,
        allowed=allowed,
        timestamp=timestamp or datetime.now(timezone.utc),
    )
    session.add(event)
    return event


class TestIncidentModel:
    async def test_create_incident(self, db_session: AsyncSession):
        now = datetime.now(timezone.utc)
        incident = Incident(
            agent_id="agent-1",
            title="Sensitive file deletion attempt",
            status=IncidentStatus.OPEN,
            severity="critical",
            started_at=now,
            updated_at=now,
        )
        db_session.add(incident)
        await db_session.commit()
        await db_session.refresh(incident)

        assert incident.id is not None
        assert incident.agent_id == "agent-1"
        assert incident.status == IncidentStatus.OPEN
        assert incident.event_count == 0

    async def test_incident_status_values(self):
        assert IncidentStatus.OPEN == "open"
        assert IncidentStatus.RESOLVED == "resolved"


class TestIncidentTracker:
    async def test_blocked_event_creates_incident(self, db_session: AsyncSession):
        now = datetime.now(timezone.utc)
        event = _make_event(
            db_session,
            agent_id="rogue-agent",
            event_type="file_delete",
            target="/app/.env",
            allowed=False,
            timestamp=now,
        )
        event.explanation_json = {"severity": "critical"}
        await db_session.commit()
        await db_session.refresh(event)

        tracker = IncidentTracker(db_session)
        incident = await tracker.track_event(event)

        assert incident is not None
        assert incident.agent_id == "rogue-agent"
        assert incident.severity == "critical"
        assert incident.status == IncidentStatus.OPEN
        assert incident.event_count == 1

    async def test_allowed_event_returns_none(self, db_session: AsyncSession):
        event = _make_event(db_session, allowed=True)
        await db_session.commit()
        await db_session.refresh(event)

        tracker = IncidentTracker(db_session)
        incident = await tracker.track_event(event)
        assert incident is None

    async def test_multiple_blocks_same_agent_merge_into_one_incident(self, db_session: AsyncSession):
        now = datetime.now(timezone.utc)
        tracker = IncidentTracker(db_session)

        e1 = _make_event(
            db_session,
            agent_id="bad-agent",
            event_type="file_delete",
            target="/app/.env",
            allowed=False,
            timestamp=now,
        )
        await db_session.commit()
        await db_session.refresh(e1)
        inc1 = await tracker.track_event(e1)

        e2 = _make_event(
            db_session,
            agent_id="bad-agent",
            event_type="shell_exec",
            target="sudo rm -rf /",
            allowed=False,
            timestamp=now + timedelta(minutes=2),
        )
        await db_session.commit()
        await db_session.refresh(e2)
        inc2 = await tracker.track_event(e2)

        assert inc1.id == inc2.id
        assert inc2.event_count == 2

    async def test_different_agents_create_separate_incidents(self, db_session: AsyncSession):
        now = datetime.now(timezone.utc)
        tracker = IncidentTracker(db_session)

        e1 = _make_event(db_session, agent_id="agent-a", allowed=False, timestamp=now)
        await db_session.commit()
        await db_session.refresh(e1)
        inc1 = await tracker.track_event(e1)

        e2 = _make_event(db_session, agent_id="agent-b", allowed=False, timestamp=now)
        await db_session.commit()
        await db_session.refresh(e2)
        inc2 = await tracker.track_event(e2)

        assert inc1.id != inc2.id

    async def test_event_outside_window_creates_new_incident(self, db_session: AsyncSession):
        now = datetime.now(timezone.utc)
        tracker = IncidentTracker(db_session, window_minutes=30)

        e1 = _make_event(db_session, agent_id="agent-1", allowed=False, timestamp=now - timedelta(hours=2))
        await db_session.commit()
        await db_session.refresh(e1)
        inc1 = await tracker.track_event(e1)

        e2 = _make_event(db_session, agent_id="agent-1", allowed=False, timestamp=now)
        await db_session.commit()
        await db_session.refresh(e2)
        inc2 = await tracker.track_event(e2)

        assert inc1.id != inc2.id

    async def test_get_timeline_returns_surrounding_events(self, db_session: AsyncSession):
        """Timeline includes allowed events from same agent around the incident."""
        now = datetime.now(timezone.utc)
        tracker = IncidentTracker(db_session)

        _make_event(
            db_session, agent_id="agent-x", target="/tmp/safe1.txt", allowed=True, timestamp=now - timedelta(minutes=5)
        )
        blocked = _make_event(
            db_session, agent_id="agent-x", event_type="file_delete", target="/app/.env", allowed=False, timestamp=now
        )
        _make_event(
            db_session, agent_id="agent-x", target="/tmp/safe2.txt", allowed=True, timestamp=now + timedelta(minutes=1)
        )
        # Unrelated agent — should NOT appear in timeline
        _make_event(db_session, agent_id="other-agent", target="/tmp/other.txt", allowed=True, timestamp=now)

        await db_session.commit()
        await db_session.refresh(blocked)
        incident = await tracker.track_event(blocked)

        timeline = await tracker.get_timeline(incident.id)

        assert len(timeline) == 3  # safe before + blocked + safe after
        agent_ids = {e.agent_id for e in timeline}
        assert agent_ids == {"agent-x"}
        # Ordered by timestamp
        assert timeline[0].timestamp <= timeline[1].timestamp <= timeline[2].timestamp


class TestIncidentAPI:
    async def _create_blocked_event(self, client, agent_id: str = "rogue-agent", target: str = "/app/.env"):
        return await client.post(
            "/api/events",
            json={
                "agent_id": agent_id,
                "source": "test",
                "event_type": "file_delete",
                "action": "delete",
                "target": target,
            },
        )

    async def test_list_incidents(self, client):
        # Create blocked events to trigger incidents
        await self._create_blocked_event(client, agent_id="agent-a", target="/app/.env")
        await self._create_blocked_event(client, agent_id="agent-b", target="/secrets/key.pem")

        resp = await client.get("/api/incidents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2
        # Each incident has expected fields
        inc = data[0]
        assert "id" in inc
        assert "agent_id" in inc
        assert "title" in inc
        assert "severity" in inc
        assert "status" in inc
        assert "event_count" in inc
        assert "started_at" in inc

    async def test_get_incident_detail(self, client):
        resp = await self._create_blocked_event(client)
        event_data = resp.json()
        assert event_data["allowed"] is False

        # List incidents to get the incident id
        list_resp = await client.get("/api/incidents")
        incidents = list_resp.json()
        assert len(incidents) >= 1
        incident_id = incidents[0]["id"]

        detail_resp = await client.get(f"/api/incidents/{incident_id}")
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert detail["id"] == incident_id
        assert detail["agent_id"] == "rogue-agent"
        assert "timeline" in detail
        assert len(detail["timeline"]) >= 1

    async def test_get_nonexistent_incident(self, client):
        from uuid import uuid4

        resp = await client.get(f"/api/incidents/{uuid4()}")
        assert resp.status_code == 404

    async def test_incident_timeline_in_detail(self, client):
        """Timeline in detail includes the blocked event with its action info."""
        await self._create_blocked_event(client, target="/secrets/private.key")

        list_resp = await client.get("/api/incidents")
        incident_id = list_resp.json()[0]["id"]

        detail_resp = await client.get(f"/api/incidents/{incident_id}")
        detail = detail_resp.json()
        timeline = detail["timeline"]
        assert any(e["target"] == "/secrets/private.key" for e in timeline)
        # Each timeline entry has required fields
        entry = timeline[0]
        assert "id" in entry
        assert "timestamp" in entry
        assert "event_type" in entry
        assert "action" in entry
        assert "target" in entry
        assert "allowed" in entry

    async def test_resolve_incident(self, client):
        await self._create_blocked_event(client)

        list_resp = await client.get("/api/incidents")
        incident_id = list_resp.json()[0]["id"]

        resolve_resp = await client.post(f"/api/incidents/{incident_id}/resolve")
        assert resolve_resp.status_code == 200
        assert resolve_resp.json()["status"] == "resolved"

        # Verify it's resolved
        detail_resp = await client.get(f"/api/incidents/{incident_id}")
        assert detail_resp.json()["status"] == "resolved"

    async def test_ack_incident(self, client):
        # TASK-004 — `bsupervisor incidents ack` needs an idempotent
        # acknowledged-state transition distinct from resolve so an
        # operator can flag triage in progress without closing the row.
        await self._create_blocked_event(client)

        list_resp = await client.get("/api/incidents")
        incident_id = list_resp.json()[0]["id"]

        ack_resp = await client.post(f"/api/incidents/{incident_id}/ack")
        assert ack_resp.status_code == 200
        assert ack_resp.json()["status"] == "acknowledged"

        detail_resp = await client.get(f"/api/incidents/{incident_id}")
        assert detail_resp.json()["status"] == "acknowledged"

    async def test_ack_nonexistent_incident(self, client):
        from uuid import uuid4

        resp = await client.post(f"/api/incidents/{uuid4()}/ack")
        assert resp.status_code == 404

    async def test_list_incidents_filter_by_severity(self, client, db_session: AsyncSession):
        # Seed two incidents at different severities directly so the
        # filter is exercised independently of the rule engine's
        # severity inference.
        now = datetime.now(timezone.utc)
        critical = Incident(
            agent_id="agent-c",
            title="critical incident",
            status=IncidentStatus.OPEN,
            severity="critical",
            event_count=1,
            started_at=now,
            updated_at=now,
            tenant_id="tenant-test",
        )
        medium = Incident(
            agent_id="agent-m",
            title="medium incident",
            status=IncidentStatus.OPEN,
            severity="medium",
            event_count=1,
            started_at=now,
            updated_at=now,
            tenant_id="tenant-test",
        )
        db_session.add_all([critical, medium])
        await db_session.commit()

        resp = await client.get("/api/incidents", params={"severity": "critical"})
        assert resp.status_code == 200
        rows = resp.json()
        assert all(r["severity"] == "critical" for r in rows)
        assert any(r["agent_id"] == "agent-c" for r in rows)
        assert not any(r["agent_id"] == "agent-m" for r in rows)

    async def test_list_incidents_filter_by_since(self, client, db_session: AsyncSession):
        now = datetime.now(timezone.utc)
        old = Incident(
            agent_id="agent-old",
            title="old incident",
            status=IncidentStatus.OPEN,
            severity="medium",
            event_count=1,
            started_at=now - timedelta(days=10),
            updated_at=now - timedelta(days=10),
            tenant_id="tenant-test",
        )
        recent = Incident(
            agent_id="agent-recent",
            title="recent incident",
            status=IncidentStatus.OPEN,
            severity="medium",
            event_count=1,
            started_at=now,
            updated_at=now,
            tenant_id="tenant-test",
        )
        db_session.add_all([old, recent])
        await db_session.commit()

        cutoff = (now - timedelta(days=1)).isoformat()
        resp = await client.get("/api/incidents", params={"since": cutoff})
        assert resp.status_code == 200
        ids = {r["agent_id"] for r in resp.json()}
        assert "agent-recent" in ids
        assert "agent-old" not in ids
