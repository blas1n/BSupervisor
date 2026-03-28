# BSupervisor

AI agent auditing and safety system. Monitors agent actions, evaluates safety rules in real time, tracks LLM costs, and generates daily reports.

## Features

- **Event ingestion** -- receives agent action events, evaluates them against safety rules, and returns allow/block decisions in the request path (<50ms p99 target)
- **Rule engine** -- built-in rules (sensitive file deletion, dangerous shell commands, cost threshold warnings) plus user-defined rules stored in PostgreSQL with glob-pattern matching
- **Cost tracking** -- records per-call LLM usage (model, tokens, cost) and aggregates daily totals per agent and model
- **Daily reports** -- generates summary reports with event counts, blocked actions, cost breakdowns by agent/model, and top agents by activity (JSON + Markdown)
- **Real-time status** -- today's event count, blocked count, and total cost at a glance

## API Endpoints

All endpoints are prefixed with `/api`.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/events` | Ingest an agent action event; returns allow/block decision |
| `GET` | `/api/status` | Today's summary (events, blocked, cost) |
| `POST` | `/api/costs` | Record an LLM usage cost entry |
| `GET` | `/api/reports/daily?date=YYYY-MM-DD` | Generate or retrieve a daily report |
| `GET` | `/api/rules` | List all audit rules |
| `POST` | `/api/rules` | Create a new rule |
| `PUT` | `/api/rules/{rule_id}` | Update an existing rule |
| `DELETE` | `/api/rules/{rule_id}` | Delete a rule |
| `GET` | `/api/health` | Health check |

### Rule Condition Format

Rules use a JSON condition object matched against incoming events:

```json
{
  "event_type": "shell_exec",
  "target_pattern": "*/secrets/*",
  "agent_id": "agent-123"
}
```

All fields are optional. `target_pattern` supports glob syntax. Rule actions: `block`, `warn`, `log`.

## Quick Start

### Using the Devcontainer (recommended)

The project includes a devcontainer configuration with PostgreSQL 16:

```bash
# Open in VS Code / Claude Code -- devcontainer starts automatically
# Then inside the container:
alembic upgrade head
uvicorn bsupervisor.main:app --host 0.0.0.0 --port 8000 --reload
```

### Manual Setup

Requires Python 3.11+ and PostgreSQL 16.

```bash
# Install dependencies
uv sync

# Set environment variables (or create .env)
export DATABASE_URL="postgresql+asyncpg://bsupervisor:bsupervisor_dev@localhost:5432/bsupervisor"

# Run migrations
alembic upgrade head

# Start server
uvicorn bsupervisor.main:app --host 0.0.0.0 --port 8000 --reload
```

## Configuration

All settings are managed via `pydantic-settings` and can be set through environment variables or a `.env` file.

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://bsupervisor:bsupervisor_dev@postgres:5432/bsupervisor` | Async PostgreSQL connection string |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `DEBUG` | `false` | Debug mode |
| `AUTH_PROVIDER` | `local` | Auth provider (`local` or bsvibe-auth) |
| `JWT_SECRET` | _(empty)_ | JWT signing secret |
| `DAILY_COST_THRESHOLD_USD` | `50.00` | Daily cost warning threshold per agent |
| `WEBHOOK_URL` | _(empty)_ | Optional webhook for notifications |

## Development

```bash
# Run tests with coverage (must be >= 80%)
python -m pytest tests/ -v --cov=bsupervisor --cov-fail-under=80

# Lint
ruff check bsupervisor/
ruff format --check bsupervisor/

# Create a migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head
```

## Architecture

```
bsupervisor/
  main.py              # FastAPI app, lifespan, router registration
  config.py            # pydantic-settings (env vars)
  api/
    events.py          # POST /api/events -- ingestion + rule evaluation
    costs.py           # POST /api/costs -- LLM cost recording
    reports.py         # GET /api/reports/daily -- daily report generation
    rules.py           # CRUD /api/rules -- user-defined audit rules
    status.py          # GET /api/status -- today's summary
    schemas.py         # Pydantic request/response models
  core/
    rule_engine.py     # Built-in + DB rules, condition matching, cost threshold
    cost_tracker.py    # Cost recording and daily aggregation
    reporter.py        # Daily report generation with Markdown rendering
  models/
    audit_event.py     # AuditEvent SQLAlchemy model
    audit_rule.py      # AuditRule SQLAlchemy model
    cost_record.py     # CostRecord SQLAlchemy model
    daily_report.py    # DailyReport SQLAlchemy model
    database.py        # Async engine, session factory
alembic/               # Database migrations
tests/                 # pytest test suite
```

Stack: Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), PostgreSQL 16, structlog, pydantic-settings.

## BSVibe Ecosystem

BSupervisor is part of the BSVibe ecosystem but works fully standalone -- it has no hard dependency on other BSVibe services. When deployed alongside BSNexus (agent orchestrator) or BSGateway (API gateway), it receives events and cost data from those systems. Auth is handled via bsvibe-auth (optional; can run with `AUTH_PROVIDER=local` for standalone use).
