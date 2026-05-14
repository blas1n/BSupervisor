"""``bsupervisor audit`` sub-app — read-only audit trail.

Subcommands:

* ``list`` → ``GET /api/events`` (most-recent-first event listing)
* ``show`` → ``GET /api/reports/daily?date=<YYYY-MM-DD>`` (daily report)

Both endpoints gate on ``bsupervisor:audit:read``. ``audit show`` deliberately
maps to the daily-report endpoint rather than a per-event detail route — the
reports surface is the canonical "what happened on day X" view, while the
events list is the streaming firehose. A future ``audit show <event-id>``
flavour would need a new GET-by-id route on the events router.
"""

from __future__ import annotations

from typing import Any

import structlog
import typer

from bsupervisor.cli._client import build_client
from bsupervisor.cli.commands._common import emit_dry_run, emit_http_error, run_async

logger = structlog.get_logger(__name__)

app = typer.Typer(
    name="audit",
    help="Read-only audit trail (events list + daily reports).",
    no_args_is_help=True,
    add_completion=False,
)


@app.command("list", help="List the most recent audit events.")
def list_cmd(ctx: typer.Context) -> None:
    obj = ctx.obj
    path = "/api/events"

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


@app.command("show", help="Show the daily audit report for a given date (YYYY-MM-DD).")
def show_cmd(
    ctx: typer.Context,
    report_date: str = typer.Argument(..., metavar="DATE", help="Report date in YYYY-MM-DD format."),
) -> None:
    obj = ctx.obj
    path = "/api/reports/daily"
    params = {"date": report_date}

    if obj.dry_run:
        emit_dry_run(obj, {"method": "GET", "path": path, "params": params})
        return

    async def _go() -> Any:
        client = build_client(obj)
        try:
            return await client.get(path, params=params)
        finally:
            await client.aclose()

    resp = run_async(_go)
    if resp.status_code >= 400:
        emit_http_error(resp)
        raise typer.Exit(code=1)
    obj.formatter.emit(resp.json())


__all__ = ["app"]
