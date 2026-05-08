"""Shared helpers for ``bsupervisor`` CLI sub-apps.

Mirrors BSGateway PR #43's ``_common.py``: a dry-run renderer, a
friendly HTTP-error printer, and a small async-runner so each sub-app
focuses on its own request shape rather than re-deriving the same
primitives.
"""

from __future__ import annotations

import asyncio
from typing import Any

import typer

__all__ = ["emit_dry_run", "emit_http_error", "run_async"]


def emit_dry_run(ctx_obj: Any, payload: dict[str, Any]) -> None:
    """Render the planned request without firing it.

    ``--dry-run`` MUST short-circuit before any network call so an AI
    agent can introspect a command without side effects (Phase 5 spec).
    """
    ctx_obj.formatter.emit({"dry_run": True, **payload})


def emit_http_error(resp: Any) -> None:
    """Print a one-line error to stderr — no stack trace.

    Bootstrap secrets are NEVER part of the response body, so logging
    the raw ``detail`` is safe; we still cap free-form ``text`` at 300
    chars to avoid pasting kilobytes of HTML on a misrouted request.
    """
    detail: Any
    try:
        body = resp.json()
    except Exception:
        body = None
    if isinstance(body, dict) and "detail" in body:
        detail = body["detail"]
    elif body is not None:
        detail = body
    else:
        detail = (resp.text or "").strip()[:300]
    typer.echo(f"Error: HTTP {resp.status_code} — {detail}", err=True)


def run_async(coro_factory: Any) -> Any:
    """Run an async coroutine factory (for build_client + aclose pattern)."""
    return asyncio.run(coro_factory())
