"""Rule engine for evaluating agent actions against safety rules."""

import asyncio
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from fnmatch import fnmatch

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.config import settings
from bsupervisor.models.audit_event import AuditEvent
from bsupervisor.models.audit_rule import AuditRule
from bsupervisor.models.cost_record import CostRecord

logger = structlog.get_logger(__name__)

SENSITIVE_EXTENSIONS = (".env", ".key", ".pem")
DANGEROUS_SHELL_PATTERNS = ("sudo", "rm -rf", "chmod 777")

_rules_cache: list[AuditRule] | None = None
_rules_cache_ts: float = 0.0
_RULES_CACHE_TTL = 30.0  # seconds
_rules_cache_lock = asyncio.Lock()


def invalidate_rules_cache() -> None:
    """Clear the rules cache so the next evaluation fetches fresh data."""
    global _rules_cache, _rules_cache_ts  # noqa: PLW0603
    _rules_cache = None
    _rules_cache_ts = 0.0


@dataclass
class RuleExplanation:
    rule_name: str
    rule_description: str
    rule_type: str  # "builtin" or "custom"
    matched_field: str
    matched_value: str
    matched_pattern: str
    severity: str
    suggestion: str | None = None


@dataclass
class RuleResult:
    allowed: bool
    rule_name: str | None = None
    reason: str | None = None
    explanation: RuleExplanation | None = None


class RuleEngine:
    def __init__(
        self,
        session: AsyncSession,
        daily_cost_threshold: Decimal | None = None,
    ) -> None:
        self.session = session
        self.daily_cost_threshold = daily_cost_threshold or settings.daily_cost_threshold_usd

    async def evaluate(self, event: AuditEvent) -> RuleResult:
        """Evaluate an event against all rules. Returns the first matching result."""
        result = self._check_sensitive_file_delete(event)
        if not result.allowed:
            logger.warning("event_blocked", rule=result.rule_name, reason=result.reason, agent_id=event.agent_id)
            return result

        result = self._check_dangerous_shell(event)
        if not result.allowed:
            logger.warning("event_blocked", rule=result.rule_name, reason=result.reason, agent_id=event.agent_id)
            return result

        result = await self._check_db_rules(event)
        if not result.allowed or result.rule_name is not None:
            if not result.allowed:
                logger.warning("event_blocked", rule=result.rule_name, reason=result.reason, agent_id=event.agent_id)
            else:
                logger.warning("event_warned", rule=result.rule_name, reason=result.reason, agent_id=event.agent_id)
            return result

        # Cost threshold is a warning, not a block — check last so block rules take priority
        result = await self._check_cost_threshold(event)
        if result.rule_name is not None:
            logger.warning("cost_threshold_exceeded", rule=result.rule_name, agent_id=event.agent_id)
            return result

        return RuleResult(allowed=True)

    def _check_sensitive_file_delete(self, event: AuditEvent) -> RuleResult:
        if event.event_type != "file_delete":
            return RuleResult(allowed=True)

        for ext in SENSITIVE_EXTENSIONS:
            if event.target.endswith(ext):
                return RuleResult(
                    allowed=False,
                    rule_name="builtin:block_sensitive_file_delete",
                    reason=f"Deleting {ext} files is not allowed",
                    explanation=RuleExplanation(
                        rule_name="builtin:block_sensitive_file_delete",
                        rule_description="Blocks deletion of sensitive credential files",
                        rule_type="builtin",
                        matched_field="target",
                        matched_value=event.target,
                        matched_pattern=ext,
                        severity="critical",
                        suggestion="Use a secrets manager instead of deleting credential files directly",
                    ),
                )
        return RuleResult(allowed=True)

    def _check_dangerous_shell(self, event: AuditEvent) -> RuleResult:
        if event.event_type != "shell_exec":
            return RuleResult(allowed=True)

        target_lower = event.target.lower()
        for pattern in DANGEROUS_SHELL_PATTERNS:
            # Check if pattern appears as a distinct command segment
            if re.search(r"(?:^|\s|;|&&|\|\|)" + re.escape(pattern), target_lower):
                return RuleResult(
                    allowed=False,
                    rule_name="builtin:block_dangerous_shell",
                    reason=f"Shell command containing '{pattern}' is blocked",
                    explanation=RuleExplanation(
                        rule_name="builtin:block_dangerous_shell",
                        rule_description="Blocks execution of dangerous shell commands",
                        rule_type="builtin",
                        matched_field="target",
                        matched_value=event.target,
                        matched_pattern=pattern,
                        severity="critical",
                        suggestion="Review the command and remove the dangerous operation",
                    ),
                )
        return RuleResult(allowed=True)

    async def _check_db_rules(self, event: AuditEvent) -> RuleResult:
        global _rules_cache, _rules_cache_ts  # noqa: PLW0603

        now = time.monotonic()
        if _rules_cache is None or (now - _rules_cache_ts) >= _RULES_CACHE_TTL:
            async with _rules_cache_lock:
                if _rules_cache is None or (time.monotonic() - _rules_cache_ts) >= _RULES_CACHE_TTL:
                    stmt = select(AuditRule).where(AuditRule.enabled.is_(True))
                    result = await self.session.execute(stmt)
                    _rules_cache = list(result.scalars().all())
                    _rules_cache_ts = time.monotonic()
                rules = _rules_cache
        else:
            # Snapshot outside the fast-path to avoid NPE if cache is invalidated mid-iteration
            rules = _rules_cache or []

        for rule in rules:
            matched_detail = self._condition_match_detail(event, rule.condition)
            if matched_detail is not None:
                severity = rule.condition.get("severity", "medium")
                explanation = RuleExplanation(
                    rule_name=rule.name,
                    rule_description=rule.description,
                    rule_type="custom",
                    matched_field=matched_detail["field"],
                    matched_value=matched_detail["value"],
                    matched_pattern=matched_detail["pattern"],
                    severity="warning" if rule.action == "warn" else severity,
                )
                if rule.action == "block":
                    return RuleResult(
                        allowed=False,
                        rule_name=rule.name,
                        reason=f"Blocked by rule: {rule.description}",
                        explanation=explanation,
                    )
                if rule.action == "warn":
                    return RuleResult(
                        allowed=True,
                        rule_name=rule.name,
                        reason=f"Warning from rule: {rule.description}",
                        explanation=explanation,
                    )
                logger.info("rule_matched", rule=rule.name, action=rule.action, agent_id=event.agent_id)

        return RuleResult(allowed=True)

    def _condition_match_detail(self, event: AuditEvent, condition: dict) -> dict | None:
        """Check if an event matches a rule condition and return match details.

        Returns None if no match, or a dict with field/value/pattern of the most
        specific matched condition.
        """
        last_match: dict | None = None

        if "event_type" in condition:
            if event.event_type != condition["event_type"]:
                return None
            last_match = {"field": "event_type", "value": event.event_type, "pattern": condition["event_type"]}

        if "action" in condition:
            if event.action != condition["action"]:
                return None
            last_match = {"field": "action", "value": event.action, "pattern": condition["action"]}

        if "target_pattern" in condition:
            if not fnmatch(event.target, condition["target_pattern"]):
                return None
            last_match = {"field": "target", "value": event.target, "pattern": condition["target_pattern"]}

        if "agent_id" in condition:
            if event.agent_id != condition["agent_id"]:
                return None
            last_match = {"field": "agent_id", "value": event.agent_id, "pattern": condition["agent_id"]}

        # If we got here, all conditions matched. Return the most specific match detail.
        # If no specific conditions were set, return a generic match.
        if last_match is None:
            return {"field": "event_type", "value": event.event_type, "pattern": "*"}

        return last_match

    async def _check_cost_threshold(self, event: AuditEvent) -> RuleResult:
        today = datetime.now(timezone.utc).date()
        stmt = select(func.coalesce(func.sum(CostRecord.cost_usd), Decimal("0"))).where(
            CostRecord.agent_id == event.agent_id,
            func.date(CostRecord.timestamp) == today,
        )
        result = await self.session.execute(stmt)
        daily_cost = result.scalar_one()

        if daily_cost > self.daily_cost_threshold:
            return RuleResult(
                allowed=True,
                rule_name="builtin:cost_threshold_warning",
                reason=f"Agent daily cost ${daily_cost} exceeds threshold ${self.daily_cost_threshold}",
                explanation=RuleExplanation(
                    rule_name="builtin:cost_threshold_warning",
                    rule_description="Warns when an agent's daily LLM cost exceeds the configured threshold",
                    rule_type="builtin",
                    matched_field="agent_id",
                    matched_value=event.agent_id,
                    matched_pattern=f"daily_cost > ${self.daily_cost_threshold}",
                    severity="warning",
                    suggestion=f"Review agent '{event.agent_id}' usage or increase the daily cost threshold",
                ),
            )
        return RuleResult(allowed=True)
