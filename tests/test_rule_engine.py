"""Tests for the rule engine."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.core.rule_engine import RuleEngine, RuleResult
from bsupervisor.models.audit_event import AuditEvent
from bsupervisor.models.audit_rule import AuditRule
from bsupervisor.models.cost_record import CostRecord


def _make_event(
    event_type: str = "file_access",
    action: str = "read",
    target: str = "/tmp/data.txt",
    agent_id: str = "agent-1",
) -> AuditEvent:
    """Create an AuditEvent instance for testing (not persisted)."""
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


# --- RuleResult dataclass ---


class TestRuleResult:
    def test_default_allowed(self):
        result = RuleResult(allowed=True)
        assert result.allowed is True
        assert result.rule_name is None
        assert result.reason is None

    def test_blocked_with_details(self):
        result = RuleResult(allowed=False, rule_name="test_rule", reason="blocked")
        assert result.allowed is False
        assert result.rule_name == "test_rule"
        assert result.reason == "blocked"


# --- Built-in rule: block sensitive file deletion ---


class TestBlockSensitiveFileDelete:
    async def test_block_delete_env_file(self, db_session: AsyncSession):
        engine = RuleEngine(db_session)
        event = _make_event(event_type="file_delete", target="/app/.env")
        result = await engine.evaluate(event)
        assert result.allowed is False
        assert result.rule_name == "builtin:block_sensitive_file_delete"
        assert ".env" in result.reason

    async def test_block_delete_key_file(self, db_session: AsyncSession):
        engine = RuleEngine(db_session)
        event = _make_event(event_type="file_delete", target="/secrets/server.key")
        result = await engine.evaluate(event)
        assert result.allowed is False
        assert ".key" in result.reason

    async def test_block_delete_pem_file(self, db_session: AsyncSession):
        engine = RuleEngine(db_session)
        event = _make_event(event_type="file_delete", target="/certs/ca.pem")
        result = await engine.evaluate(event)
        assert result.allowed is False
        assert ".pem" in result.reason

    async def test_allow_delete_normal_file(self, db_session: AsyncSession):
        engine = RuleEngine(db_session)
        event = _make_event(event_type="file_delete", target="/tmp/output.log")
        result = await engine.evaluate(event)
        assert result.allowed is True

    async def test_allow_non_delete_event_on_env_file(self, db_session: AsyncSession):
        engine = RuleEngine(db_session)
        event = _make_event(event_type="file_access", action="read", target="/app/.env")
        result = await engine.evaluate(event)
        assert result.allowed is True


# --- Built-in rule: block dangerous shell commands ---


class TestBlockDangerousShellExec:
    async def test_block_sudo(self, db_session: AsyncSession):
        engine = RuleEngine(db_session)
        event = _make_event(event_type="shell_exec", target="sudo rm /etc/passwd")
        result = await engine.evaluate(event)
        assert result.allowed is False
        assert result.rule_name == "builtin:block_dangerous_shell"
        assert "sudo" in result.reason

    async def test_block_rm_rf(self, db_session: AsyncSession):
        engine = RuleEngine(db_session)
        event = _make_event(event_type="shell_exec", target="rm -rf /")
        result = await engine.evaluate(event)
        assert result.allowed is False
        assert "rm -rf" in result.reason

    async def test_block_chmod_777(self, db_session: AsyncSession):
        engine = RuleEngine(db_session)
        event = _make_event(event_type="shell_exec", target="chmod 777 /etc/shadow")
        result = await engine.evaluate(event)
        assert result.allowed is False
        assert "chmod 777" in result.reason

    async def test_allow_safe_shell_command(self, db_session: AsyncSession):
        engine = RuleEngine(db_session)
        event = _make_event(event_type="shell_exec", target="ls -la /tmp")
        result = await engine.evaluate(event)
        assert result.allowed is True

    async def test_allow_non_shell_event(self, db_session: AsyncSession):
        engine = RuleEngine(db_session)
        event = _make_event(event_type="api_call", target="sudo.example.com/api")
        result = await engine.evaluate(event)
        assert result.allowed is True


# --- Built-in rule: warn on cost threshold ---


class TestCostThresholdWarning:
    async def test_warn_when_agent_exceeds_daily_cost(self, db_session: AsyncSession):
        # Seed cost records that exceed the default threshold (50.00)
        record = CostRecord(
            agent_id="expensive-agent",
            model="gpt-4",
            tokens_in=100000,
            tokens_out=50000,
            cost_usd=Decimal("55.00"),
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(record)
        await db_session.commit()

        engine = RuleEngine(db_session, daily_cost_threshold=Decimal("50.00"))
        event = _make_event(event_type="api_call", target="openai.com", agent_id="expensive-agent")
        result = await engine.evaluate(event)

        # Warning: still allowed but with reason
        assert result.allowed is True
        assert result.rule_name == "builtin:cost_threshold_warning"
        assert "threshold" in result.reason.lower()

    async def test_no_warn_under_threshold(self, db_session: AsyncSession):
        record = CostRecord(
            agent_id="cheap-agent",
            model="gpt-3.5",
            tokens_in=1000,
            tokens_out=500,
            cost_usd=Decimal("0.50"),
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(record)
        await db_session.commit()

        engine = RuleEngine(db_session, daily_cost_threshold=Decimal("50.00"))
        event = _make_event(event_type="api_call", target="openai.com", agent_id="cheap-agent")
        result = await engine.evaluate(event)
        assert result.allowed is True
        assert result.rule_name is None


# --- DB rules ---


class TestDBRules:
    async def test_db_rule_blocks_matching_event(self, db_session: AsyncSession):
        rule = AuditRule(
            name="block_api_delete",
            description="Block DELETE API calls",
            condition={"event_type": "api_call", "action": "delete"},
            action="block",
            enabled=True,
        )
        db_session.add(rule)
        await db_session.commit()

        engine = RuleEngine(db_session)
        event = _make_event(event_type="api_call", action="delete", target="https://api.example.com/users/1")
        result = await engine.evaluate(event)
        assert result.allowed is False
        assert result.rule_name == "block_api_delete"

    async def test_db_rule_with_target_pattern(self, db_session: AsyncSession):
        rule = AuditRule(
            name="block_prod_access",
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
        assert result.rule_name == "block_prod_access"

    async def test_db_rule_disabled_is_skipped(self, db_session: AsyncSession):
        rule = AuditRule(
            name="disabled_rule",
            description="Should be ignored",
            condition={"event_type": "file_delete"},
            action="block",
            enabled=False,
        )
        db_session.add(rule)
        await db_session.commit()

        engine = RuleEngine(db_session)
        event = _make_event(event_type="file_delete", target="/tmp/safe.txt")
        result = await engine.evaluate(event)
        assert result.allowed is True

    async def test_db_warn_rule_allows_with_reason(self, db_session: AsyncSession):
        rule = AuditRule(
            name="warn_external_api",
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
        assert result.rule_name == "warn_external_api"
        assert result.reason is not None

    async def test_db_log_rule_allows_silently(self, db_session: AsyncSession):
        rule = AuditRule(
            name="log_file_access",
            description="Log all file access",
            condition={"event_type": "file_access"},
            action="log",
            enabled=True,
        )
        db_session.add(rule)
        await db_session.commit()

        engine = RuleEngine(db_session)
        event = _make_event(event_type="file_access", target="/data/report.csv")
        result = await engine.evaluate(event)
        assert result.allowed is True

    async def test_no_db_rules_allows_event(self, db_session: AsyncSession):
        engine = RuleEngine(db_session)
        event = _make_event(event_type="unknown_type", target="anywhere")
        result = await engine.evaluate(event)
        assert result.allowed is True


# --- Integration with event API ---


class TestRuleEngineAPIIntegration:
    async def test_blocked_event_returns_allowed_false(self, client):
        """Event ingestion should use rule engine and return blocked."""
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
        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is False
        assert data["reason"] is not None
        assert ".key" in data["reason"]

    async def test_allowed_event_returns_allowed_true(self, client):
        """Safe events should pass through."""
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
        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is True

    async def test_dangerous_shell_blocked_via_api(self, client):
        """Shell exec with sudo should be blocked via API."""
        response = await client.post(
            "/api/events",
            json={
                "agent_id": "hacker-agent",
                "source": "test",
                "event_type": "shell_exec",
                "action": "exec",
                "target": "sudo rm -rf /",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is False
        assert "sudo" in data["reason"]
