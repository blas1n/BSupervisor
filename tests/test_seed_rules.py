"""Tests for default built-in safety rules seeding."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.core.seed_rules import DEFAULT_RULES, seed_default_rules
from bsupervisor.models.audit_rule import AuditRule


class TestSeedDefaultRules:
    async def test_seeds_all_default_rules_on_empty_db(self, db_session: AsyncSession):
        seeded = await seed_default_rules(db_session)
        assert seeded == len(DEFAULT_RULES)

        result = await db_session.execute(select(AuditRule))
        rules = result.scalars().all()
        assert len(rules) == len(DEFAULT_RULES)

    async def test_all_seeded_rules_are_built_in(self, db_session: AsyncSession):
        await seed_default_rules(db_session)

        result = await db_session.execute(select(AuditRule))
        rules = result.scalars().all()
        for rule in rules:
            assert rule.built_in is True

    async def test_all_seeded_rules_are_enabled(self, db_session: AsyncSession):
        await seed_default_rules(db_session)

        result = await db_session.execute(select(AuditRule))
        rules = result.scalars().all()
        for rule in rules:
            assert rule.enabled is True

    async def test_does_not_re_seed_when_built_in_rules_exist(self, db_session: AsyncSession):
        # First seed
        first_count = await seed_default_rules(db_session)
        assert first_count == len(DEFAULT_RULES)

        # Second seed should skip
        second_count = await seed_default_rules(db_session)
        assert second_count == 0

        # Total rules should still be the same
        result = await db_session.execute(select(AuditRule))
        rules = result.scalars().all()
        assert len(rules) == len(DEFAULT_RULES)

    async def test_seeds_specific_rule_names(self, db_session: AsyncSession):
        await seed_default_rules(db_session)

        result = await db_session.execute(select(AuditRule.name))
        names = {row[0] for row in result.all()}

        expected_names = {
            "SQL Injection Detection",
            "Prompt Injection Detection",
            "PII Leak Prevention",
            "Cost Threshold Alert",
            "Rate Anomaly Detection",
            "Toxic Content Filter",
            "Shell Command Blocking",
            "API Key Exposure",
        }
        assert names == expected_names

    async def test_seeded_rules_have_correct_actions(self, db_session: AsyncSession):
        await seed_default_rules(db_session)

        result = await db_session.execute(select(AuditRule))
        rules = {r.name: r for r in result.scalars().all()}

        # Block rules
        assert rules["SQL Injection Detection"].action == "block"
        assert rules["Prompt Injection Detection"].action == "block"
        assert rules["Toxic Content Filter"].action == "block"
        assert rules["Shell Command Blocking"].action == "block"
        assert rules["API Key Exposure"].action == "block"

        # Warn rules
        assert rules["PII Leak Prevention"].action == "warn"
        assert rules["Cost Threshold Alert"].action == "warn"
        assert rules["Rate Anomaly Detection"].action == "warn"

    async def test_seeded_rules_have_valid_conditions(self, db_session: AsyncSession):
        await seed_default_rules(db_session)

        result = await db_session.execute(select(AuditRule))
        rules = result.scalars().all()
        for rule in rules:
            assert "type" in rule.condition
            assert "pattern" in rule.condition
            assert "severity" in rule.condition
            assert rule.condition["type"] in ("pattern", "cost", "rate")

    async def test_default_rules_list_is_not_empty(self):
        assert len(DEFAULT_RULES) == 8

    async def test_each_default_rule_has_required_fields(self):
        for rule_data in DEFAULT_RULES:
            assert "name" in rule_data
            assert "description" in rule_data
            assert "condition" in rule_data
            assert "action" in rule_data
            assert rule_data["action"] in ("block", "warn", "log")


class TestBuiltInRuleProtection:
    async def test_cannot_delete_built_in_rule(self, client, db_session: AsyncSession):
        """Built-in rules should return 403 on delete attempt."""
        rule = AuditRule(
            name="built-in-test",
            description="A built-in rule",
            condition={"type": "pattern", "pattern": "test", "severity": "medium"},
            action="block",
            enabled=True,
            built_in=True,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        resp = await client.delete(f"/api/rules/{rule.id}")
        assert resp.status_code == 403
        assert "Built-in" in resp.json()["detail"]

    async def test_can_delete_non_built_in_rule(self, client, db_session: AsyncSession):
        """Non-built-in rules should still be deletable."""
        rule = AuditRule(
            name="custom-rule",
            description="A custom rule",
            condition={"type": "pattern", "pattern": "test", "severity": "medium"},
            action="block",
            enabled=True,
            built_in=False,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        resp = await client.delete(f"/api/rules/{rule.id}")
        assert resp.status_code == 204

    async def test_list_rules_shows_built_in_flag(self, client, db_session: AsyncSession):
        """API should correctly return the built_in flag."""
        rule = AuditRule(
            name="built-in-list-test",
            description="desc",
            condition={"type": "pattern", "pattern": "test", "severity": "medium"},
            action="block",
            enabled=True,
            built_in=True,
        )
        db_session.add(rule)
        await db_session.commit()

        resp = await client.get("/api/rules")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["built_in"] is True


class TestSeedRulesViaLifespan:
    async def test_rules_seeded_via_api_after_startup(self, client, db_session: AsyncSession):
        """After seeding, rules should be visible via the API (uses client fixture that already has DB)."""
        await seed_default_rules(db_session)

        resp = await client.get("/api/rules")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == len(DEFAULT_RULES)
        built_in_count = sum(1 for r in data if r["built_in"])
        assert built_in_count == len(DEFAULT_RULES)
