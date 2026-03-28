You are building BSupervisor from scratch — an AI agent auditing and safety system.

## Your Task

Read `.agent/tasks.json` to find the highest-priority incomplete task (passes: false, lowest priority number). Implement ONLY that one task, then update tasks.json to mark it as passes: true.

## Project Context

- **Stack**: Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), asyncpg, Alembic, structlog, pydantic-settings
- **Package manager**: uv (run commands with `uv run`)
- **Linting**: ruff (line-length 120)
- **Testing**: pytest + pytest-asyncio, asyncio_mode = "auto", coverage >= 80%
- **Test DB**: aiosqlite (in-memory SQLite for tests, asyncpg for production)

## Key Files

- `bsupervisor/main.py` — FastAPI app (currently minimal health check)
- `bsupervisor/config.py` — Pydantic settings
- `bsupervisor/models/` — SQLAlchemy models (to be created)
- `bsupervisor/core/` — Business logic (to be created)
- `bsupervisor/api/` — API routes (to be created)
- `tests/conftest.py` — Test fixtures (httpx AsyncClient)
- `alembic/` — Migration directory
- `pyproject.toml` — Dependencies

## Rules

1. **TDD**: Write failing tests BEFORE implementation code
2. **Decimal for money**: Use Decimal type for cost_usd, never float
3. **structlog** for all logging
4. **pydantic-settings** for configuration
5. **async/await** for all I/O
6. **No Co-Authored-By** in commit messages
7. Run `uv run ruff check bsupervisor/` to verify lint
8. Run `uv run pytest tests/ -v --cov=bsupervisor --cov-fail-under=80` to verify tests
9. Commit with format: `type(scope): description`
10. Event ingestion must be fast — keep rule evaluation simple and synchronous in the request path

## After completing the task

Update `.agent/tasks.json`: set the completed task's `passes` to `true`. Append findings to `.agent/progress.txt`.
