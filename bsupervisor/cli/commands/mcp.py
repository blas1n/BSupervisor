"""``bsupervisor mcp`` sub-app — boot or introspect the MCP server.

Subcommands:

* ``serve [--transport stdio|http]`` — boots the stdio MCP transport.
  ``http`` is intentionally unimplemented here: the FastAPI app already
  mounts ``/mcp`` (see :mod:`bsupervisor.mcp.sse`), so HTTP serve is
  ``uvicorn bsupervisor.main:app``.
* ``list-tools`` — prints the admin tool catalog (name + description +
  required scopes + audit event) so an operator can confirm the surface
  exposed by a given build without starting a server.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
import typer

from bsupervisor.cli.commands._common import emit_dry_run

logger = structlog.get_logger(__name__)

app = typer.Typer(
    name="mcp",
    help="Boot or introspect the BSupervisor MCP server.",
    no_args_is_help=True,
    add_completion=False,
)

VALID_TRANSPORTS = ("stdio", "http")


def _run_stdio() -> None:
    """Indirection so tests can monkey-patch the boot path without
    actually wiring stdio. Importing inside the function keeps the heavy
    ``mcp.server.stdio`` import off the CLI fast path."""

    from bsupervisor.mcp.transport import run_stdio_server

    asyncio.run(run_stdio_server())


@app.command("serve", help="Run the MCP server (stdio transport by default).")
def serve_cmd(
    ctx: typer.Context,
    transport: str = typer.Option(
        "stdio",
        "--transport",
        help="MCP transport to use. Currently only `stdio` is bootable from this CLI.",
    ),
) -> None:
    obj = ctx.obj

    if transport not in VALID_TRANSPORTS:
        raise typer.BadParameter(f"unknown transport {transport!r}. Supported: {', '.join(VALID_TRANSPORTS)}")

    if obj.dry_run:
        emit_dry_run(obj, {"action": "mcp.serve", "transport": transport})
        return

    if transport == "http":
        # The FastAPI app at ``bsupervisor.main:app`` already mounts ``/mcp``
        # via the lifespan integration. Booting another HTTP server here
        # would duplicate the surface and confuse operators.
        typer.echo(
            "Error: HTTP MCP is served by the FastAPI app — run `uvicorn bsupervisor.main:app` instead.",
            err=True,
        )
        raise typer.Exit(code=2)

    _run_stdio()


@app.command("list-tools", help="Print the admin MCP tool catalog as JSON.")
def list_tools_cmd(ctx: typer.Context) -> None:
    obj = ctx.obj
    from bsupervisor.mcp.admin_tools import ADMIN_TOOLS

    payload: list[dict[str, Any]] = [
        {
            "name": tool.name,
            "description": tool.description,
            "required_scopes": list(tool.required_scopes),
            "audit_event": tool.audit_event,
        }
        for tool in ADMIN_TOOLS
    ]
    obj.formatter.emit(payload)


__all__ = ["app"]
