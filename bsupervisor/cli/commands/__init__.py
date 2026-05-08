"""``bsupervisor.cli.commands`` — Typer sub-app modules.

Each sub-app exposes ``app`` (a :class:`typer.Typer`) that ``cli.main``
mounts via ``add_typer``. Subcommands wrap a single REST router under
``bsupervisor/api/``.
"""
