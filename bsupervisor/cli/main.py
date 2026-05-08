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

app = cli_app(
    name="bsupervisor",
    help=(
        "BSupervisor admin CLI — manage rules, triage incidents, query the "
        "audit trail, and tune runtime settings from the terminal."
    ),
)


__all__ = ["app"]
