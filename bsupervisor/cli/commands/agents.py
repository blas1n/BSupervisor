"""``bsupervisor agents`` sub-app — wraps the rule-engine REST surface.

Subcommands:

* ``list``   → ``GET    /api/rules``
* ``add``    → ``POST   /api/rules``
* ``update`` → ``PUT    /api/rules/{id}``
* ``delete`` → ``DELETE /api/rules/{id}``
* ``run``    → ``POST   /api/events`` (synthetic event → rule eval)

``run`` posts to the ingestion endpoint, which is gated by service auth
(``aud="bsupervisor"``). Use ``--token <service-jwt>`` to exercise it
from an admin shell; admin scope on a PAT works in dev/test.
"""

from __future__ import annotations

from typing import Any

import structlog
import typer

from bsupervisor.cli._client import build_client
from bsupervisor.cli.commands._common import emit_dry_run, emit_http_error, run_async

logger = structlog.get_logger(__name__)

app = typer.Typer(
    name="agents",
    help="Manage rules + run synthetic evaluations against the rule engine.",
    no_args_is_help=True,
    add_completion=False,
)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@app.command("list", help="List all rules visible to the active tenant.")
def list_cmd(ctx: typer.Context) -> None:
    obj = ctx.obj
    path = "/api/rules"

    if obj.dry_run:
        emit_dry_run(obj, {"method": "GET", "path": path})
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
    obj.formatter.emit(resp.json() or [])


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


@app.command("add", help="Create a new rule.")
def add_cmd(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", help="Rule name (unique per tenant)."),
    action: str = typer.Option(..., "--action", help="block | warn | log."),
    rule_type: str = typer.Option("pattern", "--type", help="pattern | regex | literal | action | cost | rate."),
    pattern: str = typer.Option("", "--pattern", help="Pattern string for the matcher."),
    severity: str = typer.Option("medium", "--severity", help="critical | high | medium | low | warning | info."),
    description: str = typer.Option("", "--description", help="Free-form description."),
    enabled: bool = typer.Option(True, "--enabled/--disabled", help="Enable on creation."),
) -> None:
    obj = ctx.obj
    body: dict[str, Any] = {
        "name": name,
        "type": rule_type,
        "pattern": pattern,
        "severity": severity,
        "action": action,
        "description": description,
        "enabled": enabled,
    }
    path = "/api/rules"

    if obj.dry_run:
        emit_dry_run(obj, {"method": "POST", "path": path, "body": body})
        return

    async def _go() -> Any:
        client = build_client(obj)
        try:
            return await client.post(path, json=body)
        finally:
            await client.aclose()

    resp = run_async(_go)
    if resp.status_code >= 400:
        emit_http_error(resp)
        raise typer.Exit(code=1)
    obj.formatter.emit(resp.json())


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


@app.command("update", help="Patch an existing rule (only the fields you pass).")
def update_cmd(
    ctx: typer.Context,
    rule_id: str = typer.Argument(..., help="Rule id (uuid)."),
    name: str | None = typer.Option(None, "--name"),
    rule_type: str | None = typer.Option(None, "--type"),
    pattern: str | None = typer.Option(None, "--pattern"),
    severity: str | None = typer.Option(None, "--severity"),
    action: str | None = typer.Option(None, "--action"),
    description: str | None = typer.Option(None, "--description"),
    enabled: bool | None = typer.Option(None, "--enabled/--disabled"),
) -> None:
    obj = ctx.obj
    body: dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if rule_type is not None:
        body["type"] = rule_type
    if pattern is not None:
        body["pattern"] = pattern
    if severity is not None:
        body["severity"] = severity
    if action is not None:
        body["action"] = action
    if description is not None:
        body["description"] = description
    if enabled is not None:
        body["enabled"] = enabled

    if not body:
        raise typer.BadParameter(
            "update needs at least one of --name / --type / --pattern / "
            "--severity / --action / --description / --enabled"
        )

    path = f"/api/rules/{rule_id}"

    if obj.dry_run:
        emit_dry_run(obj, {"method": "PUT", "path": path, "body": body})
        return

    async def _go() -> Any:
        client = build_client(obj)
        try:
            return await client.request("PUT", path, json=body)
        finally:
            await client.aclose()

    resp = run_async(_go)
    if resp.status_code >= 400:
        emit_http_error(resp)
        raise typer.Exit(code=1)
    obj.formatter.emit(resp.json())


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@app.command("delete", help="Delete a rule.")
def delete_cmd(
    ctx: typer.Context,
    rule_id: str = typer.Argument(..., help="Rule id (uuid)."),
    if_exists: bool = typer.Option(False, "--if-exists", help="Treat 404 as success (idempotent delete)."),
) -> None:
    obj = ctx.obj
    path = f"/api/rules/{rule_id}"

    if obj.dry_run:
        emit_dry_run(obj, {"method": "DELETE", "path": path})
        return

    async def _go() -> Any:
        client = build_client(obj)
        try:
            return await client.delete(path)
        finally:
            await client.aclose()

    resp = run_async(_go)
    if resp.status_code == 404 and if_exists:
        obj.formatter.emit({"deleted": False, "id": rule_id, "reason": "not_found"})
        return
    if resp.status_code >= 400:
        emit_http_error(resp)
        raise typer.Exit(code=1)
    obj.formatter.emit({"deleted": True, "id": rule_id})


# ---------------------------------------------------------------------------
# run — POST /api/events with a synthetic payload, surfacing the rule
# engine's allow/block decision back to the operator.
# ---------------------------------------------------------------------------


@app.command("run", help="Submit a synthetic event and surface the rule-engine decision.")
def run_cmd(
    ctx: typer.Context,
    agent_id: str = typer.Option(..., "--agent-id", help="Synthetic agent identifier."),
    source: str = typer.Option(..., "--source", help="Upstream source (cli, bsnexus, …)."),
    event_type: str = typer.Option(..., "--event-type", help="e.g. file_delete, prompt_send."),
    action: str = typer.Option(..., "--action", help="e.g. delete, read, write."),
    target: str = typer.Option(..., "--target", help="Target resource (path, url, agent…)."),
) -> None:
    obj = ctx.obj
    body: dict[str, Any] = {
        "agent_id": agent_id,
        "source": source,
        "event_type": event_type,
        "action": action,
        "target": target,
    }
    path = "/api/events"

    if obj.dry_run:
        emit_dry_run(obj, {"method": "POST", "path": path, "body": body})
        return

    async def _go() -> Any:
        client = build_client(obj)
        try:
            return await client.post(path, json=body)
        finally:
            await client.aclose()

    resp = run_async(_go)
    if resp.status_code in (401, 403) and _smells_like_audience_mismatch(resp):
        # Phase 8 dogfood (2026-05-11) caught operators running the
        # synthetic trigger with a user PAT and getting a stiff JSON
        # ``{"detail":"service JWT verification failed: Audience doesn't
        # match"}`` with no hint on what to do. ``/api/events`` is a
        # service-to-service ingress (audience=``bsupervisor``); it
        # cannot be hit directly with a user PAT. Surface a friendly
        # explanation + the correct path before bubbling exit 1.
        typer.echo(
            "Error: ``/api/events`` is a service-to-service endpoint and "
            "rejects user PATs. ``bsupervisor agents run`` is a development "
            "convenience that requires a service token.\n\n"
            "Options:\n"
            "  - Use ``--dry-run`` to inspect the request body without "
            "submitting (no auth needed).\n"
            "  - Trigger via the upstream system (BSNexus / BSGateway) "
            "whose service token has audience=`bsupervisor`. The same "
            "synthetic event will flow through the real ingress path.\n"
            "  - For ad-hoc testing in dev, mint a PAT via the BSVibe-Auth "
            "device flow and pass it via ``--token``.",
            err=True,
        )
        raise typer.Exit(code=1)
    if resp.status_code >= 400:
        emit_http_error(resp)
        raise typer.Exit(code=1)
    obj.formatter.emit(resp.json())


def _smells_like_audience_mismatch(resp: Any) -> bool:
    """Return True if the response looks like a service-audience reject.

    ``/api/events`` issues 401 when the bearer is a user PAT instead of
    a service token, embedding ``Audience doesn't match`` in the
    detail. We pattern-match that string rather than exact-match the
    full message so a future error-text refresh on the auth side
    doesn't silently regress this UX path.
    """
    try:
        body = resp.json()
    except Exception:
        return False
    detail = ""
    if isinstance(body, dict):
        detail = str(body.get("detail") or body.get("error") or "")
    return "audience" in detail.lower()


__all__ = ["app"]
