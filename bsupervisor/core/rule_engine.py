"""Rule engine for evaluating agent actions against safety rules."""

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


def invalidate_rules_cache() -> None:
    """Clear the rules cache so the next evaluation fetches fresh data."""
    global _rules_cache, _rules_cache_ts  # noqa: PLW0603
    _rules_cache = None
    _rules_cache_ts = 0.0


@dataclass
class RuleResult:
    allowed: bool
    rule_name: str | None = None
    reason: str | None = None


class RuleEngine:
    def __init__(
        self,
        session: AsyncSession,
        daily_cost_threshold: Decimal | None = None,
    ) -> None:
        self.session = session
        self.daily_cost_threshold = daily_cost_threshold or Decimal(settings.daily_cost_threshold_usd)

    async def evaluate(self, event: AuditEvent) -> RuleResult:
        """Evaluate an event against all rules. Returns the first matching result."""
        # 1. Built-in: block sensitive file deletion
        result = self._check_sensitive_file_delete(event)
        if not result.allowed:
            logger.warning("event_blocked", rule=result.rule_name, reason=result.reason, agent_id=event.agent_id)
            return result

        # 2. Built-in: block dangerous shell commands
        result = self._check_dangerous_shell(event)
        if not result.allowed:
            logger.warning("event_blocked", rule=result.rule_name, reason=result.reason, agent_id=event.agent_id)
            return result

        # 3. DB rules
        result = await self._check_db_rules(event)
        if not result.allowed or result.rule_name is not None:
            if not result.allowed:
                logger.warning("event_blocked", rule=result.rule_name, reason=result.reason, agent_id=event.agent_id)
            else:
                logger.warning("event_warned", rule=result.rule_name, reason=result.reason, agent_id=event.agent_id)
            return result

        # 4. Built-in: cost threshold warning (check last, it's a warning not a block)
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
                )
        return RuleResult(allowed=True)

    def _check_dangerous_shell(self, event: AuditEvent) -> RuleResult:
        if event.event_type != "shell_exec":
            return RuleResult(allowed=True)

        target_lower = event.target.lower()
        for pattern in DANGEROUS_SHELL_PATTERNS:
            # Check if pattern appears as a distinct command segment
            if re.search(r'(?:^|\s|;|&&|\|\|)' + re.escape(pattern), target_lower):
                return RuleResult(
                    allowed=False,
                    rule_name="builtin:block_dangerous_shell",
                    reason=f"Shell command containing '{pattern}' is blocked",
                )
        return RuleResult(allowed=True)

    async def _check_db_rules(self, event: AuditEvent) -> RuleResult:
        global _rules_cache, _rules_cache_ts  # noqa: PLW0603

        now = time.monotonic()
        if _rules_cache is None or (now - _rules_cache_ts) >= _RULES_CACHE_TTL:
            stmt = select(AuditRule).where(AuditRule.enabled.is_(True))
            result = await self.session.execute(stmt)
            _rules_cache = list(result.scalars().all())
            _rules_cache_ts = now

        rules = _rules_cache

        for rule in rules:
            if self._condition_matches(event, rule.condition):
                if rule.action == "block":
                    return RuleResult(
                        allowed=False,
                        rule_name=rule.name,
                        reason=f"Blocked by rule: {rule.description}",
                    )
                if rule.action == "warn":
                    return RuleResult(
                        allowed=True,
                        rule_name=rule.name,
                        reason=f"Warning from rule: {rule.description}",
                    )
                # action == "log": just log, no change to result
                logger.info("rule_matched", rule=rule.name, action=rule.action, agent_id=event.agent_id)

        return RuleResult(allowed=True)

    def _condition_matches(self, event: AuditEvent, condition: dict) -> bool:
        """Check if an event matches a rule condition."""
        if "event_type" in condition and event.event_type != condition["event_type"]:
            return False
        if "action" in condition and event.action != condition["action"]:
            return False
        if "target_pattern" in condition and not fnmatch(event.target, condition["target_pattern"]):
            return False
        if "agent_id" in condition and event.agent_id != condition["agent_id"]:
            return False
        return True

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
            )
        return RuleResult(allowed=True)
