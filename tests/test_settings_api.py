"""Tests for Settings API endpoints — generic integrations."""

from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.models.settings import Settings


class TestGetSettings:
    async def test_get_settings_returns_defaults_when_empty(self, client):
        resp = await client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "connections" in data
        conn = data["connections"]
        assert conn["integrations"] == []
        assert conn["telegram_bot_token"] == ""
        assert conn["slack_webhook_url"] == ""

    async def test_get_settings_returns_saved_values(self, client, db_session: AsyncSession):
        row = Settings(
            key="connections",
            value={
                "integrations": [
                    {
                        "id": "int-1",
                        "name": "My Nexus",
                        "type": "bsnexus",
                        "endpoint_url": "https://nexus.example.com",
                        "api_key": "key123",
                    },
                    {
                        "id": "int-2",
                        "name": "OpenAI Prod",
                        "type": "openai",
                        "endpoint_url": "https://api.openai.com",
                        "api_key": "sk-abc",
                    },
                ],
                "telegram_bot_token": "bot:token",
                "slack_webhook_url": "https://hooks.slack.com/test",
            },
            description="Connection settings",
        )
        db_session.add(row)
        await db_session.commit()

        resp = await client.get("/api/settings")
        assert resp.status_code == 200
        conn = resp.json()["connections"]
        assert len(conn["integrations"]) == 2
        assert conn["integrations"][0]["name"] == "My Nexus"
        assert conn["integrations"][0]["type"] == "bsnexus"
        assert conn["integrations"][1]["name"] == "OpenAI Prod"
        assert conn["integrations"][1]["type"] == "openai"
        assert conn["telegram_bot_token"] == "bot:token"


class TestUpdateSettings:
    async def test_update_settings_creates_new_record(self, client):
        payload = {
            "integrations": [
                {
                    "id": "int-1",
                    "name": "My BSNexus",
                    "type": "bsnexus",
                    "endpoint_url": "https://nexus.bsvibe.dev",
                    "api_key": "sk-test",
                },
            ],
            "telegram_bot_token": "",
            "slack_webhook_url": "",
        }
        resp = await client.put("/api/settings", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["connections"]["integrations"]) == 1
        assert data["connections"]["integrations"][0]["name"] == "My BSNexus"
        assert data["connections"]["integrations"][0]["type"] == "bsnexus"

    async def test_update_settings_overwrites_existing(self, client, db_session: AsyncSession):
        row = Settings(
            key="connections",
            value={
                "integrations": [
                    {
                        "id": "int-old",
                        "name": "Old",
                        "type": "custom",
                        "endpoint_url": "http://old.dev",
                        "api_key": "",
                    },
                ],
                "telegram_bot_token": "",
                "slack_webhook_url": "",
            },
            description="Connection settings",
        )
        db_session.add(row)
        await db_session.commit()

        payload = {
            "integrations": [
                {
                    "id": "int-new",
                    "name": "New Platform",
                    "type": "anthropic",
                    "endpoint_url": "https://api.anthropic.com",
                    "api_key": "sk-ant-123",
                },
            ],
            "telegram_bot_token": "tg",
            "slack_webhook_url": "slack",
        }
        resp = await client.put("/api/settings", json=payload)
        assert resp.status_code == 200
        conn = resp.json()["connections"]
        assert len(conn["integrations"]) == 1
        assert conn["integrations"][0]["name"] == "New Platform"
        assert conn["integrations"][0]["type"] == "anthropic"

        # Verify persisted
        resp2 = await client.get("/api/settings")
        assert resp2.json()["connections"]["integrations"][0]["name"] == "New Platform"

    async def test_update_settings_rejects_extra_fields(self, client):
        payload = {
            "integrations": [],
            "telegram_bot_token": "",
            "slack_webhook_url": "",
            "unknown_field": "value",
        }
        resp = await client.put("/api/settings", json=payload)
        assert resp.status_code == 422

    async def test_update_settings_validates_integration_type(self, client):
        payload = {
            "integrations": [
                {
                    "id": "int-1",
                    "name": "Bad",
                    "type": "invalid_type",
                    "endpoint_url": "http://x",
                    "api_key": "",
                },
            ],
            "telegram_bot_token": "",
            "slack_webhook_url": "",
        }
        resp = await client.put("/api/settings", json=payload)
        assert resp.status_code == 422

    async def test_update_settings_multiple_integrations(self, client):
        payload = {
            "integrations": [
                {
                    "id": "int-1",
                    "name": "BSNexus",
                    "type": "bsnexus",
                    "endpoint_url": "https://nexus.bsvibe.dev",
                    "api_key": "sk-1",
                },
                {
                    "id": "int-2",
                    "name": "BSGateway",
                    "type": "bsgateway",
                    "endpoint_url": "https://gateway.bsvibe.dev",
                    "api_key": "",
                },
                {
                    "id": "int-3",
                    "name": "OpenAI",
                    "type": "openai",
                    "endpoint_url": "https://api.openai.com",
                    "api_key": "sk-oai",
                },
            ],
            "telegram_bot_token": "bot:tok",
            "slack_webhook_url": "",
        }
        resp = await client.put("/api/settings", json=payload)
        assert resp.status_code == 200
        conn = resp.json()["connections"]
        assert len(conn["integrations"]) == 3


class TestSettingsModel:
    async def test_settings_model_crud(self, db_session: AsyncSession):
        row = Settings(
            key="test_key",
            value={"hello": "world"},
            description="Test setting",
        )
        db_session.add(row)
        await db_session.commit()
        await db_session.refresh(row)

        assert row.id is not None
        assert row.key == "test_key"
        assert row.value == {"hello": "world"}
