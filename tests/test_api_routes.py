"""Tests for TASK-006: API routes — status, rules CRUD, lifespan."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.models.audit_event import AuditEvent
from bsupervisor.models.audit_rule import AuditRule
from bsupervisor.models.cost_record import CostRecord


# ---------------------------------------------------------------------------
# GET /api/status
# ---------------------------------------------------------------------------


class TestStatusEndpoint:
    async def test_status_empty_db(self, client):
        resp = await client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["events_today"] == 0
        assert data["violations"] == 0
        assert data["blocked_actions"] == 0
        assert data["cost_total"] == "$0"

    async def test_status_with_events_and_costs(self, client, db_session: AsyncSession):
        now = datetime.now(timezone.utc)

        # Add some events
        for i in range(3):
            db_session.add(
                AuditEvent(
                    agent_id="agent-1",
                    source="test",
                    event_type="action",
                    action="run",
                    target="/tmp/test",
                    allowed=True,
                    timestamp=now,
                )
            )
        # Add a blocked event
        db_session.add(
            AuditEvent(
                agent_id="agent-2",
                source="test",
                event_type="action",
                action="delete",
                target="/etc/passwd",
                allowed=False,
                timestamp=now,
            )
        )
        # Add cost records
        db_session.add(
            CostRecord(
                agent_id="agent-1",
                model="gpt-4",
                tokens_in=100,
                tokens_out=50,
                cost_usd=Decimal("1.50"),
                timestamp=now,
            )
        )
        db_session.add(
            CostRecord(
                agent_id="agent-2",
                model="claude-sonnet",
                tokens_in=200,
                tokens_out=100,
                cost_usd=Decimal("0.75"),
                timestamp=now,
            )
        )
        await db_session.commit()

        resp = await client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["events_today"] == 4
        assert data["violations"] == 1
        assert data["blocked_actions"] == 1
        assert data["cost_total"] == "$2.25"


# ---------------------------------------------------------------------------
# GET /api/rules
# ---------------------------------------------------------------------------


class TestListRules:
    async def test_list_rules_empty(self, client):
        resp = await client.get("/api/rules")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_rules_returns_all(self, client, db_session: AsyncSession):
        for i in range(3):
            db_session.add(
                AuditRule(
                    name=f"rule-{i}",
                    description=f"desc {i}",
                    condition={"event_type": "test"},
                    action="block",
                    enabled=True,
                )
            )
        await db_session.commit()

        resp = await client.get("/api/rules")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        assert all("id" in r for r in data)
        assert all("name" in r for r in data)


# ---------------------------------------------------------------------------
# POST /api/rules
# ---------------------------------------------------------------------------


class TestCreateRule:
    async def test_create_rule(self, client):
        payload = {
            "name": "block-env-delete",
            "type": "pattern",
            "pattern": "*.env",
            "severity": "critical",
            "action": "block",
            "description": "Block .env file deletion",
        }
        resp = await client.post("/api/rules", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "block-env-delete"
        assert data["action"] == "block"
        assert data["type"] == "pattern"
        assert data["pattern"] == "*.env"
        assert data["severity"] == "critical"
        assert data["enabled"] is True
        assert data["built_in"] is False
        assert "id" in data

    async def test_create_rule_default_enabled(self, client):
        payload = {
            "name": "warn-rule",
            "type": "action",
            "pattern": "shell_exec",
            "severity": "medium",
            "action": "warn",
            "description": "A warning rule",
        }
        resp = await client.post("/api/rules", json=payload)
        assert resp.status_code == 201
        assert resp.json()["enabled"] is True

    async def test_create_rule_invalid_action(self, client):
        payload = {
            "name": "bad-rule",
            "type": "pattern",
            "pattern": "test",
            "severity": "medium",
            "action": "invalid_action",
        }
        resp = await client.post("/api/rules", json=payload)
        assert resp.status_code == 422

    async def test_create_rule_missing_name(self, client):
        payload = {
            "type": "pattern",
            "pattern": "test",
            "severity": "medium",
            "action": "block",
        }
        resp = await client.post("/api/rules", json=payload)
        assert resp.status_code == 422

    async def test_create_rule_duplicate_name(self, client):
        payload = {
            "name": "unique-rule",
            "type": "pattern",
            "pattern": "test",
            "severity": "medium",
            "action": "block",
            "description": "First",
        }
        resp = await client.post("/api/rules", json=payload)
        assert resp.status_code == 201

        resp2 = await client.post("/api/rules", json=payload)
        assert resp2.status_code == 409


# ---------------------------------------------------------------------------
# PUT /api/rules/{id}
# ---------------------------------------------------------------------------


class TestUpdateRule:
    async def test_update_rule(self, client, db_session: AsyncSession):
        rule = AuditRule(
            name="old-name",
            description="old desc",
            condition={"event_type": "test"},
            action="warn",
            enabled=True,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        update_payload = {
            "name": "new-name",
            "description": "new desc",
            "action": "block",
            "enabled": False,
        }
        resp = await client.put(f"/api/rules/{rule.id}", json=update_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "new-name"
        assert data["description"] == "new desc"
        assert data["action"] == "block"
        assert data["enabled"] is False

    async def test_update_rule_partial(self, client, db_session: AsyncSession):
        rule = AuditRule(
            name="keep-name",
            description="keep desc",
            condition={"event_type": "test"},
            action="warn",
            enabled=True,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        resp = await client.put(f"/api/rules/{rule.id}", json={"enabled": False})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "keep-name"
        assert data["enabled"] is False

    async def test_update_rule_not_found(self, client):
        fake_id = str(uuid.uuid4())
        resp = await client.put(f"/api/rules/{fake_id}", json={"enabled": False})
        assert resp.status_code == 404

    async def test_update_rule_invalid_action(self, client, db_session: AsyncSession):
        rule = AuditRule(
            name="test-rule",
            description="desc",
            condition={"event_type": "test"},
            action="warn",
            enabled=True,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        resp = await client.put(f"/api/rules/{rule.id}", json={"action": "bad"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/rules/{id}
# ---------------------------------------------------------------------------


class TestDeleteRule:
    async def test_delete_rule(self, client, db_session: AsyncSession):
        rule = AuditRule(
            name="to-delete",
            description="will be deleted",
            condition={"event_type": "test"},
            action="block",
            enabled=True,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        resp = await client.delete(f"/api/rules/{rule.id}")
        assert resp.status_code == 204

        # Verify it's gone
        resp2 = await client.get("/api/rules")
        assert len(resp2.json()) == 0

    async def test_delete_rule_not_found(self, client):
        fake_id = str(uuid.uuid4())
        resp = await client.delete(f"/api/rules/{fake_id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Lifespan / health check still works
# ---------------------------------------------------------------------------


class TestLifespan:
    async def test_health_check(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
