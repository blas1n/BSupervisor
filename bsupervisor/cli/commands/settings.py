"""``bsupervisor settings`` sub-app — runtime config get / set.

Subcommands:

* ``get [KEY]`` → ``GET /api/settings``. Without ``KEY``, emits the full
  ``SettingsResponse``. With ``KEY``, drills into a known scalar field
  (``slack_webhook_url`` / ``telegram_bot_token``) and emits a
  ``{"key": ..., "value": ...}`` envelope.
* ``set KEY VALUE`` → round-trips through ``GET /api/settings`` to
  preserve untouched fields, applies the patch, then ``PUT
  /api/settings`` with the merged ``ConnectionSettings`` body.

Only the scalar webhook / token fields are settable from the CLI today.
``integrations`` is a structured list and would need its own
sub-commands (``settings integrations add/remove``) — out of scope for
TASK-005.
"""

from __future__ import annotations

from typing import Any

import structlog
import typer

from bsupervisor.cli._client import build_client
from bsupervisor.cli.commands._common import emit_dry_run, emit_http_error, run_async

logger = structlog.get_logger(__name__)

app = typer.Typer(
    name="settings",
    help="Runtime configuration (get / set scalar connection fields).",
    no_args_is_help=True,
    add_completion=False,
)

# Whitelisted CLI keys → field name on ``ConnectionSettings``. Centralised so
# ``get`` and ``set`` share the same surface and the same error message.
_SETTABLE_KEYS = ("slack_webhook_url", "telegram_bot_token")


@app.command("get", help="Show all settings or one whitelisted scalar key.")
def get_cmd(
    ctx: typer.Context,
    key: str | None = typer.Argument(None, metavar="[KEY]", help="Optional key to drill into."),
) -> None:
    obj = ctx.obj
    path = "/api/settings"

    if obj.dry_run:
        payload: dict[str, Any] = {"method": "GET", "path": path}
        if key is not None:
            payload["key"] = key
        emit_dry_run(obj, payload)
        return

    async def _go() -> Any:
        client = build_client(obj)
        try:
            return await client.get(path)
        finally:
            await client.aclose()

    resp = run_async(_go)
    if resp.status_code >= 400:
        emit_http_error(resp)
        raise typer.Exit(code=1)
    body = resp.json()
    if key is None:
        obj.formatter.emit(body)
        return

    if key not in _SETTABLE_KEYS:
        typer.echo(
            f"Error: unknown key {key!r}. Supported: {', '.join(_SETTABLE_KEYS)}",
            err=True,
        )
        raise typer.Exit(code=1)
    connections = body.get("connections", {}) if isinstance(body, dict) else {}
    obj.formatter.emit({"key": key, "value": connections.get(key, "")})


@app.command("set", help="Set a whitelisted scalar key (round-trips through GET).")
def set_cmd(
    ctx: typer.Context,
    key: str = typer.Argument(..., help="Setting key (slack_webhook_url | telegram_bot_token)."),
    value: str = typer.Argument(..., help="New value."),
) -> None:
    if key not in _SETTABLE_KEYS:
        raise typer.BadParameter(f"unknown key {key!r}. Supported: {', '.join(_SETTABLE_KEYS)}")

    obj = ctx.obj
    path = "/api/settings"

    if obj.dry_run:
        emit_dry_run(
            obj,
            {"method": "PUT", "path": path, "patch": {key: value}},
        )
        return

    async def _go() -> Any:
        client = build_client(obj)
        try:
            current = await client.get(path)
            if current.status_code >= 400:
                return ("get", current)
            current_body = current.json() or {}
            connections = current_body.get("connections") or {}
            patched: dict[str, Any] = {
                "integrations": connections.get("integrations", []),
                "telegram_bot_token": connections.get("telegram_bot_token", ""),
                "slack_webhook_url": connections.get("slack_webhook_url", ""),
            }
            patched[key] = value
            put_resp = await client.request("PUT", path, json=patched)
            return ("put", put_resp)
        finally:
            await client.aclose()

    stage, resp = run_async(_go)
    if resp.status_code >= 400:
        emit_http_error(resp)
        raise typer.Exit(code=1)
    if stage == "get":
        # Defensive: ``run_async`` only returns ("get", _) when GET errored,
        # so we treat the missing PUT as a hard fail.
        raise typer.Exit(code=1)
    obj.formatter.emit(resp.json())


__all__ = ["app"]
