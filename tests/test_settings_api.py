"""Tests for Settings API endpoints."""

from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.models.settings import Settings


class TestGetSettings:
    async def test_get_settings_returns_defaults_when_empty(self, client):
        resp = await client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "connections" in data
        conn = data["connections"]
        assert conn["bsnexus_url"] == ""
        assert conn["bsnexus_api_key"] == ""
        assert conn["bsgateway_url"] == ""
        assert conn["bsage_url"] == ""
        assert conn["telegram_bot_token"] == ""
        assert conn["slack_webhook_url"] == ""

    async def test_get_settings_returns_saved_values(self, client, db_session: AsyncSession):
        # Pre-populate settings
        row = Settings(
            key="connections",
            value={
                "bsnexus_url": "https://nexus.example.com",
                "bsnexus_api_key": "key123",
                "bsgateway_url": "https://gateway.example.com",
                "bsage_url": "https://sage.example.com",
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
        assert conn["bsnexus_url"] == "https://nexus.example.com"
        assert conn["bsnexus_api_key"] == "key123"
        assert conn["bsgateway_url"] == "https://gateway.example.com"
        assert conn["bsage_url"] == "https://sage.example.com"


class TestUpdateSettings:
    async def test_update_settings_creates_new_record(self, client):
        payload = {
            "bsnexus_url": "https://nexus.bsvibe.dev",
            "bsnexus_api_key": "sk-test",
            "bsgateway_url": "https://gateway.bsvibe.dev",
            "bsage_url": "",
            "telegram_bot_token": "",
            "slack_webhook_url": "",
        }
        resp = await client.put("/api/settings", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["connections"]["bsnexus_url"] == "https://nexus.bsvibe.dev"
        assert data["connections"]["bsnexus_api_key"] == "sk-test"

    async def test_update_settings_overwrites_existing(self, client, db_session: AsyncSession):
        # First save
        row = Settings(
            key="connections",
            value={
                "bsnexus_url": "old",
                "bsnexus_api_key": "",
                "bsgateway_url": "",
                "bsage_url": "",
                "telegram_bot_token": "",
                "slack_webhook_url": "",
            },
            description="Connection settings",
        )
        db_session.add(row)
        await db_session.commit()

        # Update
        payload = {
            "bsnexus_url": "new",
            "bsnexus_api_key": "key",
            "bsgateway_url": "gw",
            "bsage_url": "sage",
            "telegram_bot_token": "tg",
            "slack_webhook_url": "slack",
        }
        resp = await client.put("/api/settings", json=payload)
        assert resp.status_code == 200
        conn = resp.json()["connections"]
        assert conn["bsnexus_url"] == "new"
        assert conn["bsgateway_url"] == "gw"

        # Verify persisted
        resp2 = await client.get("/api/settings")
        assert resp2.json()["connections"]["bsnexus_url"] == "new"

    async def test_update_settings_rejects_extra_fields(self, client):
        payload = {
            "bsnexus_url": "",
            "bsnexus_api_key": "",
            "bsgateway_url": "",
            "bsage_url": "",
            "telegram_bot_token": "",
            "slack_webhook_url": "",
            "unknown_field": "value",
        }
        resp = await client.put("/api/settings", json=payload)
        assert resp.status_code == 422


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
