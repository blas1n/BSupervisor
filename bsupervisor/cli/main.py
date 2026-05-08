"""Top-level Typer app for ``bsupervisor`` admin CLI.

Built on :func:`bsvibe_cli_base.cli_app` — the root callback resolves
profile / token / tenant / output and stashes a
:class:`bsvibe_cli_base.CliContext` on ``ctx.obj`` for sub-commands.

Sub-apps land in TASK-004..005:

* ``bsupervisor agents …``    — rule / agent CRUD + run
* ``bsupervisor incidents …`` — incident triage (list / show / ack / resolve)
* ``bsupervisor audit …``     — read-only audit trail (events + reports)
* ``bsupervisor costs …``     — cost reports
* ``bsupervisor settings …``  — runtime config get / set
"""

from __future__ import annotations

from bsvibe_cli_base import cli_app

from bsupervisor.cli.commands.agents import app as agents_app
from bsupervisor.cli.commands.audit import app as audit_app
from bsupervisor.cli.commands.costs import app as costs_app
from bsupervisor.cli.commands.incidents import app as incidents_app
from bsupervisor.cli.commands.mcp import app as mcp_app
from bsupervisor.cli.commands.settings import app as settings_app

app = cli_app(
    name="bsupervisor",
    help=(
        "BSupervisor admin CLI — manage rules, triage incidents, query the "
        "audit trail, and tune runtime settings from the terminal."
    ),
)

app.add_typer(agents_app, name="agents")
app.add_typer(incidents_app, name="incidents")
app.add_typer(audit_app, name="audit")
app.add_typer(costs_app, name="costs")
app.add_typer(settings_app, name="settings")
app.add_typer(mcp_app, name="mcp")


__all__ = ["app"]
