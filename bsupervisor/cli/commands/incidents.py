"""``bsupervisor incidents`` sub-app — wraps the incidents REST surface.

Subcommands:

* ``list``    → ``GET  /api/incidents`` with optional ``--severity`` / ``--since`` filters
* ``show``    → ``GET  /api/incidents/{id}``
* ``ack``     → ``POST /api/incidents/{id}/ack``
* ``resolve`` → ``POST /api/incidents/{id}/resolve``

``ack`` puts the incident in the ``acknowledged`` state — distinct from
``resolve`` so an operator can flag triage in progress without closing
the row. Both transitions are gated by ``bsupervisor:incidents:write``.
"""

from __future__ import annotations

from typing import Any

import structlog
import typer

from bsupervisor.cli._client import build_client
from bsupervisor.cli.commands._common import emit_dry_run, emit_http_error, run_async

logger = structlog.get_logger(__name__)

app = typer.Typer(
    name="incidents",
    help="Triage incidents (list / show / ack / resolve).",
    no_args_is_help=True,
    add_completion=False,
)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@app.command("list", help="List incidents (most recent first).")
def list_cmd(
    ctx: typer.Context,
    severity: str | None = typer.Option(
        None, "--severity", help="Filter by severity (critical | high | medium | low)."
    ),
    since: str | None = typer.Option(
        None, "--since", help="ISO-8601 cutoff — only incidents updated at/after this time."
    ),
) -> None:
    obj = ctx.obj
    path = "/api/incidents"
    params: dict[str, str] = {}
    if severity:
        params["severity"] = severity
    if since:
        params["since"] = since

    if obj.dry_run:
        payload: dict[str, Any] = {"method": "GET", "path": path}
        if params:
            payload["params"] = params
        emit_dry_run(obj, payload)
        return

    async def _go() -> Any:
        client = build_client(obj)
        try:
            return await client.get(path, params=params or None)
        finally:
            await client.aclose()

    resp = run_async(_go)
    if resp.status_code >= 400:
        emit_http_error(resp)
        raise typer.Exit(code=1)
    obj.formatter.emit(resp.json() or [])


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


@app.command("show", help="Show one incident with its forensic timeline.")
def show_cmd(
    ctx: typer.Context,
    incident_id: str = typer.Argument(..., help="Incident id (uuid)."),
) -> None:
    obj = ctx.obj
    path = f"/api/incidents/{incident_id}"

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
    obj.formatter.emit(resp.json())


# ---------------------------------------------------------------------------
# ack
# ---------------------------------------------------------------------------


@app.command("ack", help="Acknowledge an incident (mark triage in progress).")
def ack_cmd(
    ctx: typer.Context,
    incident_id: str = typer.Argument(..., help="Incident id (uuid)."),
) -> None:
    _transition(ctx, incident_id, "ack")


# ---------------------------------------------------------------------------
# resolve
# ---------------------------------------------------------------------------


@app.command("resolve", help="Resolve an incident (close the row).")
def resolve_cmd(
    ctx: typer.Context,
    incident_id: str = typer.Argument(..., help="Incident id (uuid)."),
) -> None:
    _transition(ctx, incident_id, "resolve")


def _transition(ctx: typer.Context, incident_id: str, verb: str) -> None:
    obj = ctx.obj
    path = f"/api/incidents/{incident_id}/{verb}"

    if obj.dry_run:
        emit_dry_run(obj, {"method": "POST", "path": path})
        return

    async def _go() -> Any:
        client = build_client(obj)
        try:
            return await client.post(path)
        finally:
            await client.aclose()

    resp = run_async(_go)
    if resp.status_code >= 400:
        emit_http_error(resp)
        raise typer.Exit(code=1)
    obj.formatter.emit(resp.json())


__all__ = ["app"]
