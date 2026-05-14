# BSupervisor MCP

First-class MCP API surface for BSupervisor. Tools are defined on equal
footing with REST routes — explicit Pydantic input/output schemas, async
handler that calls the same service-layer functions REST handlers call,
`required_scopes` enforced via the same `bsvibe_authz` semantics, and
optional `audit_event` that fires on success.

The CLI is a presentation layer. MCP is its own API. There is **no typer
auto-adapter**: every tool is hand-written against the same service
functions the CLI and REST router call.

## Layout

```
bsupervisor/mcp/
  api.py           # Tool primitive, ToolContext, ToolRegistry dispatcher
  auth.py          # auth dispatch (opaque / JWT) → ToolContext
  admin_tools.py   # 14 admin tools + ADMIN_TOOLS / build_admin_registry
  server.py        # build_server(registry, context_provider) factory
  transport.py     # mcp_lifespan + /mcp ASGI mount + run_stdio_server
```

CLI launcher: `bsupervisor/cli/commands/mcp.py` — `bsupervisor mcp serve`
and `bsupervisor mcp list-tools`.

## Tool primitive

```python
from bsupervisor.mcp.api import Tool, ToolContext, ToolRegistry

class MyInput(BaseModel):
    foo: str

class MyOutput(BaseModel):
    result: str

async def _handler(args: MyInput, ctx: ToolContext) -> MyOutput:
    # Call service-layer function shared with REST.
    return MyOutput(result=f"hello {args.foo}")

Tool(
    name="bsupervisor_my_tool",
    description="Short human description shown in ListTools.",
    input_schema=MyInput,
    output_schema=MyOutput,
    handler=_handler,
    required_scopes=["bsupervisor:my:write"],
    audit_event="supervisor.my.executed",  # mutating tools only
)
```

Dispatcher contract (`ToolRegistry.call_tool`):

1. Validate args against `input_schema` (ValidationError → `ToolInputError`).
2. Enforce `required_scopes` against `ctx.user.scopes` using the same
   wildcard semantics as `bsvibe_authz.require_scope`
   (`"*"`, `"bsupervisor:*"`, exact match).
3. Run handler.
4. Validate handler return against `output_schema`.
5. If `audit_event` is set, emit on success only via `ctx.audit_emit`.

Transports are agnostic: the same registry serves HTTP `/mcp` and stdio.

## Adding a new tool

1. Define Pydantic input + output models. Reuse existing service-layer
   models when the shape already exists (e.g. `RuleResponse`).
2. Write an async handler `(args, ctx) -> output_model` that calls the
   service function the REST router uses. Do not duplicate business
   logic in the handler.
3. Pick `required_scopes` matching the REST route's `require_scope`.
4. Set `audit_event` if the tool mutates state. Match the REST router's
   audit event name so MCP and REST share one audit trail.
5. Append the `Tool(...)` to `ADMIN_TOOLS` in `admin_tools.py`.
6. Add a test in `tests/mcp/test_admin_tools.py` — ListTools name
   assertion + at least one CallTool round-trip.

Tests must use the in-process pattern (no subprocesses): build a
`ToolRegistry`, call `registry.call_tool(name, args, ctx)` directly, or
extract `server.request_handlers[CallToolRequest]` and invoke it with a
bound request — the result is wrapped in `ServerResult.root`.

## Catalog

Domain tools today: none. Future domain tools (e.g. `evaluate_event`,
`query_incident`) register against the same `ToolRegistry` returned by
`build_admin_registry()`.

Admin tools (14, all `bsupervisor_<subapp>_<action>`):

| Tool | Scope | Audit event |
| --- | --- | --- |
| `bsupervisor_agents_list` | `bsupervisor:agents:read` | — |
| `bsupervisor_agents_add` | `bsupervisor:agents:write` | `supervisor.rule.created` |
| `bsupervisor_agents_update` | `bsupervisor:agents:write` | `supervisor.rule.updated` |
| `bsupervisor_agents_delete` | `bsupervisor:agents:write` | `supervisor.rule.deleted` |
| `bsupervisor_agents_run` | `bsupervisor:agents:write` | `supervisor.event.evaluated` |
| `bsupervisor_incidents_list` | `bsupervisor:incidents:read` | — |
| `bsupervisor_incidents_show` | `bsupervisor:incidents:read` | — |
| `bsupervisor_incidents_ack` | `bsupervisor:incidents:write` | `supervisor.incident.acknowledged` |
| `bsupervisor_incidents_resolve` | `bsupervisor:incidents:write` | `supervisor.incident.resolved` |
| `bsupervisor_audit_list` | `bsupervisor:audit:read` | — |
| `bsupervisor_audit_show` | `bsupervisor:audit:read` | — |
| `bsupervisor_costs_report` | `bsupervisor:audit:read` | — |
| `bsupervisor_settings_get` | `bsupervisor:*` | — |
| `bsupervisor_settings_set` | `bsupervisor:*` | `supervisor.settings.updated` |

Source of truth: `ADMIN_TOOLS` / `ADMIN_TOOL_NAMES` in
`bsupervisor/mcp/admin_tools.py`. The exact event names emitted are
those declared on the `Tool` definitions there.

## HTTP `/mcp` endpoint

`mcp_lifespan` (in `transport.py`) is composed into the FastAPI
`lifespan` in `bsupervisor/main.py`. It builds the admin registry,
owns the `StreamableHTTPSessionManager` anyio task group for the life
of the process, and pins both onto `app.state`.

- `/mcp` — streamable-HTTP transport (`json_response=True`,
  stateless). Auth: `Authorization: Bearer <token>` per request.
  The HTTP context provider captures the header into a `ContextVar`
  before delegating to the session manager and resets it after, so
  each call gets a freshly resolved `ToolContext`.
- `/mcp/health` — no-auth liveness probe. Returns
  `{"status": "ok", "tool_count": <count>}`. Registered before the
  `/mcp` ASGI mount so the route table picks the FastAPI handler.

Example (after `BSUPERVISOR_PAT` is set):

```bash
curl -sS http://localhost:8000/mcp/health
# {"status":"ok","tool_count":14}
```

## stdio launcher

```bash
# default transport is stdio (Claude Desktop entry)
bsupervisor mcp serve

# or explicitly
bsupervisor mcp serve --transport stdio

# list the catalog without starting a server
bsupervisor mcp list-tools
```

`--transport http` is rejected with a uvicorn-redirect hint: the
FastAPI app is the source of truth for the HTTP transport, so run
`uvicorn bsupervisor.main:app` instead.

stdio reads `BSUPERVISOR_PAT` from env once at startup; the context
provider returns the same `ToolContext` for every call. The token is
never logged — auth-failure logs only the token prefix discriminant
(`bsv_sk_` / `?`).

## Auth resolution

`resolve_tool_context` in `auth.py` mirrors
`bsvibe_authz.deps.get_current_user`:

1. `bsv_sk_*` → opaque-token introspection (when introspection client
   is configured).
2. otherwise → user JWT (`parse_user_token`).

Failure raises `MCPAuthError`; the HTTP transport translates it to a
`ToolPermissionError` response, and stdio surfaces it as an MCP error.

## Coverage

`bsupervisor/mcp/` runs at >=94% line coverage; the full suite gates
at `--cov-fail-under=80`.

```bash
uv run pytest --cov=bsupervisor --cov-fail-under=80
uv run ruff check bsupervisor/
uv run ruff format --check bsupervisor/
```
