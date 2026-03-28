# CLAUDE.md

Project instructions for Claude Code when working on BSupervisor.

## Project Overview

BSupervisor is an AI agent auditing and safety system. It monitors AI agent actions across the BSVibe ecosystem, logs behavior, detects risks, blocks dangerous actions, and generates reports. It can be used independently with any agent system, not just BSNexus.

## Core Stack

- **Python 3.11+** / **FastAPI** (async monolith)
- **PostgreSQL 16** + SQLAlchemy 2.0 (async) + Alembic
- **structlog** for structured JSON logging
- **pydantic-settings** for configuration
- **Package manager**: `uv`
- **Linting**: `ruff` (line-length 120)
- **Auth**: bsvibe-auth

## Project Structure

```
bsupervisor/           # Main package
  api/                 # FastAPI route handlers
  core/                # Business logic (rule engine, cost tracker, reporter)
  models/              # SQLAlchemy models
  config.py            # Pydantic settings
  main.py              # App entry point

tests/                 # Test suite
alembic/               # Database migrations
```

## Development Commands

```bash
# Run server
uvicorn bsupervisor.main:app --host 0.0.0.0 --port 8000 --reload

# Tests
python -m pytest tests/ -v --cov=bsupervisor --cov-fail-under=80

# Linting
ruff check bsupervisor/
ruff format --check bsupervisor/

# Migrations
alembic upgrade head
alembic revision --autogenerate -m "description"
```

## Architecture Rules

- MUST: Use async/await for all I/O operations
- MUST: Use type hints on all public functions
- MUST: Use structlog for logging (not print or logging)
- MUST: Use pydantic-settings for config (not os.getenv)
- MUST: Use Decimal for monetary values
- MUST: Validate all external inputs with Pydantic models
- NEVER: Use `sys.path.insert`
- NEVER: Use `requirements.txt` — use `pyproject.toml` + `uv`
- NEVER: Hardcode secrets or API keys
- NEVER: Include `Co-Authored-By` in commit messages
- NEVER: Use synchronous blocking I/O

## Testing

- All code must have tests (>=80% coverage)
- Use `pytest` + `pytest-asyncio`
- Mock all external dependencies
- Use `aiosqlite` for test DB

## Design Principles

- Event ingestion must be fast (<50ms p99)
- Rule evaluation is synchronous in the request path (block/allow decision)
- Must work standalone (no BSNexus dependency)
- All provider integrations are optional with fallbacks
