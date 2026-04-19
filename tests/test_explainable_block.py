"""Tests for the Explainable Block feature.

Verifies that rule evaluation produces structured explanations:
- Which rule matched and why
- What part of the input triggered the match
- Actionable suggestions
- False positive feedback
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.core.rule_engine import RuleEngine, RuleExplanation, RuleResult
from bsupervisor.models.audit_event import AuditEvent
from bsupervisor.models.audit_rule import AuditRule
from bsupervisor.models.cost_record import CostRecord


def _make_event(
    event_type: str = "file_access",
    action: str = "read",
    target: str = "/tmp/data.txt",
    agent_id: str = "agent-1",
) -> AuditEvent:
    return AuditEvent(
        id=uuid4(),
        agent_id=agent_id,
        source="test",
        event_type=event_type,
        action=action,
        target=target,
        allowed=True,
        timestamp=datetime.now(timezone.utc),
    )


# --- RuleExplanation dataclass ---


class TestRuleExplanation:
    def test_create_explanation(self):
        expl = RuleExplanation(
            rule_name="builtin:block_sensitive_file_delete",
            rule_description="Blocks deletion of sensitive credential files",
            rule_type="builtin",
            matched_field="target",
            matched_value="/app/.env",
            matched_pattern=".env",
            severity="critical",
            suggestion="Use a secrets manager instead of deleting credential files directly",
        )
        assert expl.rule_name == "builtin:block_sensitive_file_delete"
        assert expl.matched_field == "target"
        assert expl.severity == "critical"

    def test_explanation_to_dict(self):
        expl = RuleExplanation(
            rule_name="test_rule",
            rule_description="Test",
            rule_type="builtin",
            matched_field="target",
            matched_value="/app/.env",
            matched_pattern=".env",
            severity="high",
        )
        d = expl.to_dict()
        assert d["rule_name"] == "test_rule"
        assert d["matched_field"] == "target"
        assert "suggestion" not in d or d["suggestion"] is None

    def test_rule_result_with_explanation(self):
        expl = RuleExplanation(
            rule_name="test",
            rule_description="Test rule",
            rule_type="builtin",
            matched_field="target",
            matched_value="val",
            matched_pattern="pat",
            severity="high",
        )
        result = RuleResult(allowed=False, rule_name="test", reason="blocked", explanation=expl)
        assert result.explanation is not None
        assert result.explanation.rule_name == "test"

    def test_rule_result_without_explanation(self):
        result = RuleResult(allowed=True)
        assert result.explanation is None


# --- Built-in rules produce explanations ---


class TestBuiltinExplanations:
    async def test_sensitive_file_delete_explanation(self, db_session: AsyncSession):
        engine = RuleEngine(db_session)
        event = _make_event(event_type="file_delete", target="/app/.env")
        result = await engine.evaluate(event)

        assert result.allowed is False
        assert result.explanation is not None
        assert result.explanation.rule_type == "builtin"
        assert result.explanation.matched_field == "target"
        assert result.explanation.matched_value == "/app/.env"
        assert result.explanation.matched_pattern == ".env"
        assert result.explanation.severity == "critical"
        assert result.explanation.suggestion is not None

    async def test_dangerous_shell_explanation(self, db_session: AsyncSession):
        engine = RuleEngine(db_session)
        event = _make_event(event_type="shell_exec", target="sudo rm /etc/passwd")
        result = await engine.evaluate(event)

        assert result.allowed is False
        assert result.explanation is not None
        assert result.explanation.rule_type == "builtin"
        assert result.explanation.matched_field == "target"
        assert result.explanation.matched_value == "sudo rm /etc/passwd"
        assert result.explanation.matched_pattern == "sudo"
        assert result.explanation.severity == "critical"

    async def test_cost_threshold_explanation(self, db_session: AsyncSession):
        record = CostRecord(
            agent_id="costly-agent",
            model="gpt-4",
            tokens_in=100000,
            tokens_out=50000,
            cost_usd=Decimal("55.00"),
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(record)
        await db_session.commit()

        engine = RuleEngine(db_session, daily_cost_threshold=Decimal("50.00"))
        event = _make_event(event_type="api_call", target="openai.com", agent_id="costly-agent")
        result = await engine.evaluate(event)

        assert result.allowed is True
        assert result.explanation is not None
        assert result.explanation.rule_type == "builtin"
        assert result.explanation.severity == "warning"
        assert result.explanation.matched_field == "agent_id"

    async def test_allowed_event_has_no_explanation(self, db_session: AsyncSession):
        engine = RuleEngine(db_session)
        event = _make_event(event_type="file_access", target="/tmp/safe.txt")
        result = await engine.evaluate(event)

        assert result.allowed is True
        assert result.explanation is None


# --- DB rules produce explanations ---


class TestDBRuleExplanations:
    async def test_db_block_rule_explanation(self, db_session: AsyncSession):
        rule = AuditRule(
            name="block_prod_db",
            description="Block access to production databases",
            condition={"event_type": "db_query", "target_pattern": "*production*"},
            action="block",
            enabled=True,
        )
        db_session.add(rule)
        await db_session.commit()

        engine = RuleEngine(db_session)
        event = _make_event(event_type="db_query", target="production-db.internal:5432")
        result = await engine.evaluate(event)

        assert result.allowed is False
        assert result.explanation is not None
        assert result.explanation.rule_name == "block_prod_db"
        assert result.explanation.rule_type == "custom"
        assert result.explanation.rule_description == "Block access to production databases"
        assert result.explanation.matched_field == "target"
        assert result.explanation.matched_pattern == "*production*"

    async def test_db_warn_rule_explanation(self, db_session: AsyncSession):
        rule = AuditRule(
            name="warn_external",
            description="Warn on external API calls",
            condition={"event_type": "api_call"},
            action="warn",
            enabled=True,
        )
        db_session.add(rule)
        await db_session.commit()

        engine = RuleEngine(db_session)
        event = _make_event(event_type="api_call", target="https://external.com")
        result = await engine.evaluate(event)

        assert result.allowed is True
        assert result.explanation is not None
        assert result.explanation.rule_name == "warn_external"
        assert result.explanation.severity == "warning"


# --- API response includes explanation ---


class TestExplainableBlockAPI:
    async def test_blocked_event_response_includes_explanation(self, client):
        response = await client.post(
            "/api/events",
            json={
                "agent_id": "rogue-agent",
                "source": "test",
                "event_type": "file_delete",
                "action": "delete",
                "target": "/secrets/private.key",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["allowed"] is False
        assert data["explanation"] is not None
        assert data["explanation"]["rule_name"] == "builtin:block_sensitive_file_delete"
        assert data["explanation"]["matched_field"] == "target"
        assert data["explanation"]["matched_value"] == "/secrets/private.key"
        assert data["explanation"]["matched_pattern"] == ".key"
        assert data["explanation"]["severity"] == "critical"

    async def test_allowed_event_response_has_no_explanation(self, client):
        response = await client.post(
            "/api/events",
            json={
                "agent_id": "good-agent",
                "source": "test",
                "event_type": "file_access",
                "action": "read",
                "target": "/tmp/data.txt",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["allowed"] is True
        assert data["explanation"] is None

    async def test_explanation_stored_in_event(self, client, db_session: AsyncSession):
        response = await client.post(
            "/api/events",
            json={
                "agent_id": "rogue-agent",
                "source": "test",
                "event_type": "shell_exec",
                "action": "exec",
                "target": "sudo reboot",
            },
        )
        data = response.json()
        event_id = data["event_id"]

        from sqlalchemy import select

        from bsupervisor.models.audit_event import AuditEvent

        result = await db_session.execute(select(AuditEvent).where(AuditEvent.id == UUID(event_id)))
        event = result.scalar_one()
        assert event.explanation_json is not None
        assert event.explanation_json["rule_name"] == "builtin:block_dangerous_shell"


# --- False positive feedback ---


class TestFalsePositiveFeedback:
    async def test_submit_feedback(self, client, db_session: AsyncSession):
        # First create a blocked event
        resp = await client.post(
            "/api/events",
            json={
                "agent_id": "agent-1",
                "source": "test",
                "event_type": "file_delete",
                "action": "delete",
                "target": "/app/.env.example",
            },
        )
        event_id = resp.json()["event_id"]

        # Submit false positive feedback
        feedback_resp = await client.post(
            f"/api/events/{event_id}/feedback",
            json={
                "is_false_positive": True,
                "comment": "This is .env.example, not .env — safe to delete",
            },
        )
        assert feedback_resp.status_code == 200
        data = feedback_resp.json()
        assert data["event_id"] == event_id
        assert data["accepted"] is True

    async def test_feedback_on_nonexistent_event(self, client):
        fake_id = str(uuid4())
        resp = await client.post(
            f"/api/events/{fake_id}/feedback",
            json={"is_false_positive": True, "comment": "test"},
        )
        assert resp.status_code == 404

    async def test_feedback_stored_on_event(self, client, db_session: AsyncSession):
        # Create blocked event
        resp = await client.post(
            "/api/events",
            json={
                "agent_id": "agent-1",
                "source": "test",
                "event_type": "file_delete",
                "action": "delete",
                "target": "/app/cert.pem",
            },
        )
        event_id = resp.json()["event_id"]

        # Submit feedback
        await client.post(
            f"/api/events/{event_id}/feedback",
            json={"is_false_positive": True, "comment": "test cert, not production"},
        )

        from sqlalchemy import select

        from bsupervisor.models.audit_event import AuditEvent

        result = await db_session.execute(select(AuditEvent).where(AuditEvent.id == UUID(event_id)))
        event = result.scalar_one()
        assert event.feedback_json is not None
        assert event.feedback_json["is_false_positive"] is True
        assert event.feedback_json["comment"] == "test cert, not production"
