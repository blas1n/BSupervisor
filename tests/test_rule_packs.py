"""Tests for Rule Template Packs.

Pre-built rule collections organized by industry/framework
that can be installed with a single API call.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.core.rule_packs import RULE_PACKS, get_pack, list_packs
from bsupervisor.models.audit_rule import AuditRule


# --- Pack registry ---


class TestRulePackRegistry:
    def test_list_packs_returns_all(self):
        packs = list_packs()
        assert len(packs) >= 3
        ids = {p["id"] for p in packs}
        assert "healthcare-hipaa" in ids
        assert "financial-compliance" in ids
        assert "langchain-agent" in ids

    def test_each_pack_has_required_fields(self):
        for pack in list_packs():
            assert "id" in pack
            assert "name" in pack
            assert "description" in pack
            assert "category" in pack
            assert "rule_count" in pack
            assert pack["rule_count"] > 0

    def test_get_pack_returns_pack_with_rules(self):
        pack = get_pack("healthcare-hipaa")
        assert pack is not None
        assert pack["id"] == "healthcare-hipaa"
        assert "rules" in pack
        assert len(pack["rules"]) == pack["rule_count"]

    def test_get_nonexistent_pack_returns_none(self):
        assert get_pack("nonexistent") is None

    def test_pack_rules_have_required_fields(self):
        for pack_def in RULE_PACKS:
            for rule in pack_def["rules"]:
                assert "name" in rule
                assert "description" in rule
                assert "condition" in rule
                assert "action" in rule
                assert rule["action"] in ("block", "warn", "log")

    def test_pack_categories(self):
        categories = {p["category"] for p in list_packs()}
        assert "healthcare" in categories
        assert "finance" in categories
        assert "ai-framework" in categories

    def test_no_duplicate_rule_names_within_pack(self):
        for pack_def in RULE_PACKS:
            names = [r["name"] for r in pack_def["rules"]]
            assert len(names) == len(set(names)), f"Duplicate rule names in pack {pack_def['id']}"


# --- Pack installation ---


class TestRulePackInstallation:
    async def test_install_pack_creates_rules(self, client, db_session: AsyncSession):
        resp = await client.post("/api/rule-packs/healthcare-hipaa/install")
        assert resp.status_code == 200
        data = resp.json()
        assert data["installed"] > 0
        assert data["pack_id"] == "healthcare-hipaa"

        # Verify rules in DB
        result = await db_session.execute(select(AuditRule))
        rules = result.scalars().all()
        assert len(rules) == data["installed"]

    async def test_install_pack_marks_as_built_in(self, client, db_session: AsyncSession):
        await client.post("/api/rule-packs/financial-compliance/install")

        result = await db_session.execute(select(AuditRule))
        rules = result.scalars().all()
        for rule in rules:
            assert rule.built_in is True

    async def test_install_pack_skips_existing_rules(self, client, db_session: AsyncSession):
        # Install once
        resp1 = await client.post("/api/rule-packs/healthcare-hipaa/install")
        first_count = resp1.json()["installed"]

        # Install again
        resp2 = await client.post("/api/rule-packs/healthcare-hipaa/install")
        assert resp2.status_code == 200
        assert resp2.json()["installed"] == 0
        assert resp2.json()["skipped"] == first_count

    async def test_install_nonexistent_pack(self, client):
        resp = await client.post("/api/rule-packs/nonexistent/install")
        assert resp.status_code == 404

    async def test_list_packs_api(self, client):
        resp = await client.get("/api/rule-packs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 3
        assert all("id" in p for p in data)
        assert all("name" in p for p in data)

    async def test_get_pack_detail_api(self, client):
        resp = await client.get("/api/rule-packs/langchain-agent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "langchain-agent"
        assert "rules" in data
        assert len(data["rules"]) > 0

    async def test_get_nonexistent_pack_api(self, client):
        resp = await client.get("/api/rule-packs/fake-pack")
        assert resp.status_code == 404
