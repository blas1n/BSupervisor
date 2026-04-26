"""Sprint 4 — remaining Audit §6 BSupervisor gap edges.

Audit §6 lists the BSupervisor test gaps as:

* 음수 ``cost_usd`` 거부  → covered by ``test_cost_tracker.py``
* 규칙 조건 키 오타 매칭 → covered by ``test_rule_engine.py``
* regex 컴파일 실패 핸들링 → N/A (BSupervisor's matcher uses ``fnmatch``
  + literal keys, never ``re.compile``). The audit assumed regex-based
  matching that doesn't exist in this codebase. We document that with a
  positive assertion below.
* 메타데이터 크기 제한 → no current limit. We document that existing
  behavior accepts arbitrary metadata so a future limit shows up as a
  failing test (regression-by-intent).

This file also adds a few cross-cutting integration regressions that fall
between Sprint 1 (security) and Sprint 2 (perf) hardening so a refactor
touching either alone gets caught:

* Built-in ``block_sensitive_file_delete`` + DB rule with overlapping
  ``target_pattern`` — built-ins must run first (security takes
  precedence).
* Cost-threshold warning interacts with the rule cache invalidation
  (creating a DB rule must NOT swallow built-in warnings).
* The list-events endpoint includes the explanation block on blocked
  rows (Sprint 1 added explanation; Sprint 2's perf indices must not
  hide the field).
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.core import rule_engine as rule_engine_mod
from bsupervisor.models.audit_rule import AuditRule


# ---------------------------------------------------------------------------
# Audit §6: regex compile failure — N/A documentation
# ---------------------------------------------------------------------------


class TestMatcherDoesNotUseRegex:
    """Document that the matcher path never compiles a regex.

    Audit §6 listed "regex 컴파일 실패 핸들링" as a gap, but inspection
    shows ``rule_engine._condition_match_detail`` uses ``fnmatch``, equality,
    and dictionary lookups — never ``re.compile``. The seed-rules ``pattern``
    field is metadata for the UI; the engine ignores it. This test guards
    against a refactor that *adds* regex-based matching without considering
    compile failures.
    """

    def test_rule_engine_module_does_not_call_re_compile(self) -> None:
        """A search for ``re.compile`` in the matcher module must come up empty."""
        from pathlib import Path

        source = Path(rule_engine_mod.__file__).read_text()
        # ``re.search`` is used for the dangerous-shell command boundary check;
        # that's fine — the regex literal is constant. We only block ``re.compile``
        # being applied to *user-supplied* patterns from the DB.
        # Therefore: if ``re.compile`` ever appears in this file, future-us must
        # add explicit error handling for compile failures.
        assert "re.compile" not in source, (
            "rule_engine.py now uses re.compile — add try/except re.error "
            "with fail-closed semantics and update Audit §6."
        )

    def test_dangerous_shell_pattern_uses_constant_regex(self) -> None:
        """The one constant regex in the matcher must compile cleanly."""
        for pattern in rule_engine_mod.DANGEROUS_SHELL_PATTERNS:
            # Each pattern is wrapped with a constant boundary expression — the
            # full expression must compile without error.
            full = r"(?:^|\s|;|&&|\|\|)" + re.escape(pattern)
            re.compile(full)  # would raise re.error if malformed


# ---------------------------------------------------------------------------
# Audit §6: metadata size — current behaviour documentation
# ---------------------------------------------------------------------------


class TestMetadataLargePayloadAccepted:
    """Audit §6 noted no metadata size limit. Document current behaviour.

    A future PR adding a 4 KiB / 64 KiB cap on ``metadata`` MUST update
    this test. Until then we want a regression-on-shape guard so we know
    the request path doesn't blow up on large payloads either.
    """

    async def test_large_metadata_accepted_currently(self, client) -> None:
        # 32 KiB metadata blob.
        big_metadata = {"blob": "x" * (32 * 1024)}
        resp = await client.post(
            "/api/events",
            json={
                "agent_id": "agent-meta",
                "source": "src",
                "event_type": "file_access",
                "action": "read",
                "target": "/tmp/x",
                "metadata": big_metadata,
            },
        )
        # Current behaviour: accepted. When a size limit is added this should
        # become 413 / 422 — update the assertion at that time.
        assert resp.status_code == 201

    async def test_metadata_persisted_round_trip(self, client) -> None:
        meta = {"nested": {"k": "v"}, "list": [1, 2, 3]}
        post = await client.post(
            "/api/events",
            json={
                "agent_id": "agent-meta-rt",
                "source": "src",
                "event_type": "file_access",
                "action": "read",
                "target": "/tmp/x",
                "metadata": meta,
            },
        )
        assert post.status_code == 201

        # The list endpoint omits metadata by design — verify it doesn't
        # accidentally leak it (audit-trail surface area).
        listing = await client.get("/api/events")
        assert listing.status_code == 200
        for item in listing.json():
            assert "metadata" not in item or item["metadata"] in (None, {})

    @pytest.mark.parametrize("target_length", [1024, 1023])
    async def test_target_max_length_boundary(self, client, target_length: int) -> None:
        """Schema enforces ``target`` max_length=1024 — boundary regression."""
        resp = await client.post(
            "/api/events",
            json={
                "agent_id": "a",
                "source": "s",
                "event_type": "file_access",
                "action": "read",
                "target": "/" + ("x" * (target_length - 1)),
            },
        )
        assert resp.status_code == 201

    async def test_target_over_max_length_rejected(self, client) -> None:
        resp = await client.post(
            "/api/events",
            json={
                "agent_id": "a",
                "source": "s",
                "event_type": "file_access",
                "action": "read",
                "target": "x" * 1025,
            },
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Sprint 1 + Sprint 2 cross-cutting integration regressions
# ---------------------------------------------------------------------------


class TestBuiltInRunsBeforeDbRule:
    async def test_builtin_sensitive_delete_takes_priority(
        self,
        client,
        db_session: AsyncSession,
    ) -> None:
        """Even with an overlapping warn-rule in DB, built-in block must win."""
        # DB rule that would warn (allow with reason) on the same target.
        db_session.add(
            AuditRule(
                name="overlapping_warn",
                description="overlap",
                condition={"event_type": "file_delete", "target_pattern": "*.env"},
                action="warn",
                enabled=True,
            )
        )
        await db_session.commit()

        resp = await client.post(
            "/api/events",
            json={
                "agent_id": "a",
                "source": "s",
                "event_type": "file_delete",
                "action": "delete",
                "target": "/etc/.env",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        # Built-in rule wins → blocked, not warned.
        assert body["allowed"] is False
        assert body["explanation"]["rule_name"] == "builtin:block_sensitive_file_delete"


class TestExplanationFieldOnListedEvents:
    """Sprint 1 added the explanation block; Sprint 2's index work must keep it."""

    async def test_listed_blocked_event_includes_explanation(self, client) -> None:
        await client.post(
            "/api/events",
            json={
                "agent_id": "a",
                "source": "s",
                "event_type": "file_delete",
                "action": "delete",
                "target": "/etc/server.key",
            },
        )

        resp = await client.get("/api/events")
        assert resp.status_code == 200
        rows = resp.json()
        blocked_rows = [r for r in rows if r["severity"] == "blocked"]
        assert blocked_rows, "blocked event should appear in listing"
        assert blocked_rows[0]["explanation"] is not None
        assert blocked_rows[0]["explanation"]["matched_field"] == "target"

    async def test_listed_safe_event_omits_explanation(self, client) -> None:
        await client.post(
            "/api/events",
            json={
                "agent_id": "a",
                "source": "s",
                "event_type": "file_access",
                "action": "read",
                "target": "/tmp/safe.txt",
            },
        )
        resp = await client.get("/api/events")
        rows = resp.json()
        safe_rows = [r for r in rows if r["severity"] == "safe"]
        assert safe_rows
        assert safe_rows[0]["explanation"] is None


class TestRuleCacheInteractionWithBuiltins:
    """Adding a DB rule must not invalidate the built-in pipeline."""

    async def test_create_rule_does_not_break_builtins(
        self,
        client,
    ) -> None:
        # Create a custom warn rule via API (which should invalidate the cache).
        resp = await client.post(
            "/api/rules",
            json={
                "name": "warn-on-stuff",
                "type": "pattern",
                "pattern": "stuff",
                "severity": "medium",
                "action": "warn",
                "description": "a custom warn rule",
            },
        )
        assert resp.status_code == 201

        # A built-in violation must still block.
        ev = await client.post(
            "/api/events",
            json={
                "agent_id": "a",
                "source": "s",
                "event_type": "shell_exec",
                "action": "exec",
                "target": "rm -rf /",
            },
        )
        assert ev.status_code == 201
        body = ev.json()
        assert body["allowed"] is False
        assert "rm -rf" in body["reason"]


class TestNegativeCostRegression:
    """Audit §H7 — negative cost MUST be rejected at API boundary."""

    async def test_post_cost_negative_amount_rejected(self, client) -> None:
        resp = await client.post(
            "/api/costs",
            json={
                "agent_id": "a",
                "model": "gpt-4",
                "tokens_in": 1,
                "tokens_out": 1,
                "cost_usd": "-0.01",
            },
        )
        assert resp.status_code == 422

    async def test_negative_cost_rejection_does_not_corrupt_real_spend(
        self,
        client,
    ) -> None:
        """A 422 on negative cost must not leave a partial row or skew totals."""
        # Insert a legitimate $1.00 cost.
        legit = await client.post(
            "/api/costs",
            json={
                "agent_id": "a",
                "model": "gpt-4",
                "tokens_in": 1,
                "tokens_out": 1,
                "cost_usd": "1.00",
            },
        )
        assert legit.status_code == 201

        # Reject the negative one.
        bad = await client.post(
            "/api/costs",
            json={
                "agent_id": "a",
                "model": "gpt-4",
                "tokens_in": 1,
                "tokens_out": 1,
                "cost_usd": "-1.00",
            },
        )
        assert bad.status_code == 422

        # Confirm spent total reflects only the legit row.
        listing = await client.get("/api/costs")
        assert listing.status_code == 200
        spent = listing.json()["spent"]
        assert spent == "$1.00", f"unexpected spent total: {spent}"
