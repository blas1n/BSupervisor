"""``bsupervisor costs`` sub-app — cost reports.

Subcommand:

* ``report`` → ``GET /api/costs`` with optional ``--days N`` and
  ``--by tenant|model`` query params.

The ``--by`` flag is whitelisted at the CLI boundary so an operator
can't typo a grouping mode and have it silently fall through to the
server. Server-side aggregation by tenant or model is server-side
work; today's GET endpoint returns the "today + 30-day trend" payload
unchanged regardless of these params, but forwarding them keeps the
CLI surface stable while the server backfills.
"""

from __future__ import annotations

from typing import Any

import structlog
import typer

from bsupervisor.cli._client import build_client
from bsupervisor.cli.commands._common import emit_dry_run, emit_http_error, run_async

logger = structlog.get_logger(__name__)

app = typer.Typer(
    name="costs",
    help="Cost reports (today's spend + 30-day trend, optional grouping).",
    no_args_is_help=True,
    add_completion=False,
)

_VALID_BY = ("tenant", "model")


@app.command("report", help="Show today's cost summary and 30-day trend.")
def report_cmd(
    ctx: typer.Context,
    days: int | None = typer.Option(None, "--days", help="Trend window length in days (server-side hint)."),
    by: str | None = typer.Option(None, "--by", help="Group breakdown by 'tenant' or 'model' (server-side hint)."),
) -> None:
    if by is not None and by not in _VALID_BY:
        raise typer.BadParameter(f"--by must be one of {_VALID_BY}, got {by!r}")

    obj = ctx.obj
    path = "/api/costs"
    params: dict[str, str] = {}
    if days is not None:
        params["days"] = str(days)
    if by is not None:
        params["by"] = by

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
    obj.formatter.emit(resp.json())


__all__ = ["app"]
