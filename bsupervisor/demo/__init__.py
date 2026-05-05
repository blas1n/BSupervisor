"""BSupervisor demo backend module.

BSupervisor's data model has no tenant scoping (audit_events, rules,
cost_records, daily_reports are global). Per-visitor isolation is not
enforced at the data layer; instead, the demo:

- Pre-seeds dashboard data ONCE at container startup (operator runs
  ``bsupervisor demo-seed`` against a fresh demo PG).
- Issues a JWT on POST /api/v1/demo/session so the frontend can call
  authenticated endpoints during the visit.
- Disables write endpoints in demo mode (visitors browse but can't
  modify shared state).

For products that do tenant-scope (BSGateway, BSNexus), per-visitor
ephemeral tenants are used instead — see those products' demo modules.
"""
