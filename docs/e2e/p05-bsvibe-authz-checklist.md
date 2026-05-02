# Phase 0 P0.5 — bsvibe-authz integration e2e checklist

Non-web product (FastAPI backend). Each item is verified by Claude
inspecting code or running scripted tests; each test maps to a unit /
integration test in `tests/test_p05_*.py`.

## Auth surface

- [x] `bsupervisor.api.deps` exports `CurrentUser`, `ServiceKeyAuth`,
      `bsupervisor_service_auth`, `require_permission` from bsvibe-authz
      (test_p05_authz_integration::TestDepsReExports)
- [x] `get_current_user` is the bsvibe-authz dependency (no local
      override) — test_get_current_user_uses_bsvibe_authz

## Service JWT verification

- [x] Valid `aud="bsupervisor"` + audience-prefixed scope accepted
- [x] Foreign audience (`aud="bsage"`) rejected
- [x] Foreign-prefix scope (`scope="bsage.read"` with `aud="bsupervisor"`)
      rejected (defence-in-depth)
- [x] Expired token rejected (test_expired_rejected)

## POST /api/events service-only

- [x] Valid service JWT scoped to `aud="bsupervisor"` accepted (201)
- [x] User JWT rejected (401/403)
- [x] Anonymous request rejected (401/403)
- [x] Sprint 1 H6 rate limiter still preserved (429 on overflow) —
      test_sprint4_events_rate_limit_e2e suite passes

## require_permission per route

- [x] `GET /api/rules` — `bsupervisor.rules.read`
- [x] `POST /api/rules` — `bsupervisor.rules.write`
- [x] `PUT/DELETE /api/rules/{id}` — `bsupervisor.rules.write`
- [x] `GET /api/rule-packs(/...)` — `bsupervisor.rules.read`
- [x] `POST /api/rule-packs/{id}/install` — `bsupervisor.rules.write`
- [x] `GET /api/incidents(/...)` — `bsupervisor.incidents.read`
- [x] `POST /api/incidents/{id}/resolve` — `bsupervisor.incidents.write`
- [x] `GET /api/anomalies` — `bsupervisor.anomalies.read`
- [x] `GET /api/costs` — `bsupervisor.costs.read`
- [x] `POST /api/costs` — service-only (no permission required, JWT verified)
- [x] `GET /api/reports/daily` — `bsupervisor.reports.read`
- [x] `GET /api/settings` — `bsupervisor.config.read`
- [x] `PUT /api/settings` — `bsupervisor.config.write`
- [x] `GET /api/status` — `bsupervisor.status.read`
- [x] `GET /api/events` — `bsupervisor.events.read`
- [x] `POST /api/events/{id}/feedback` — `bsupervisor.events.write`
- [x] Route matrix snapshot test catches drift
      (test_matrix_keys_cover_every_protected_route)
- [x] OpenFGA deny → 403 (test_get_rules_denied_returns_403)

## tenant_id columns

- [x] `audit_events.tenant_id` (String, nullable, indexed)
- [x] `audit_rules.tenant_id`
- [x] `cost_records.tenant_id`
- [x] `daily_reports.tenant_id`
- [x] `incidents.tenant_id`
- [x] Alembic migration 0004 adds columns + per-table index
- [x] DDL only — no data backfill

## Sprint 1 / 2 / 4 regression

- [x] H5 encryption (test_sprint4_encryption_policy_integration)
- [x] H6 rate limit (test_sprint4_events_rate_limit_e2e)
- [x] Audit §M5 cost trend single-aggregate
      (test_sprint4_cost_trend_query_regression)
- [x] Audit §M6 indexes (test_indexes)
- [x] Audit §M17 daily budget config (test_costs_api)
- [x] Audit §M18 CORS pydantic-settings (test_main_cors)
- [x] Audit §M20 DB pool sizing (test_database_pool)
- [x] Sprint 4 service JWT shape contract (17 tests passing unchanged)

## User actions

- [ ] Apply `packages/bsvibe-authz/schema/bsvibe.fga` to `_infra` OpenFGA
      store; record `OPENFGA_STORE_ID` + `OPENFGA_AUTH_MODEL_ID`.
- [ ] Generate `SERVICE_TOKEN_SIGNING_SECRET` and add to Mac Mini
      Supervisor production env.
- [ ] Mirror BSVibe-Auth's `service_token_signing_secret` into the
      Supervisor production `.env` so service tokens issued by Auth
      verify on Supervisor.
