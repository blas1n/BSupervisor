"""Default built-in safety rules seeded on first startup."""

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.models.audit_rule import AuditRule

logger = structlog.get_logger(__name__)

DEFAULT_RULES: list[dict] = [
    {
        "name": "SQL Injection Detection",
        "description": "Detects common SQL injection patterns such as UNION SELECT, DROP TABLE, and comment-based injections.",
        "condition": {
            "type": "pattern",
            "pattern": r"(?i)(\bUNION\s+SELECT\b|\bDROP\s+TABLE\b|\bDELETE\s+FROM\b|';\s*--|\b1\s*=\s*1\b|\bOR\s+1\s*=\s*1\b)",
            "severity": "critical",
        },
        "action": "block",
    },
    {
        "name": "Prompt Injection Detection",
        "description": "Detects jailbreak and prompt injection phrases that attempt to override system instructions.",
        "condition": {
            "type": "pattern",
            "pattern": r"(?i)(ignore\s+(previous|all)\s+instructions|you\s+are\s+now|act\s+as\s+(?:if|a|an)|do\s+anything\s+now|DAN\s+mode|jailbreak|system\s+prompt\s+override)",
            "severity": "critical",
        },
        "action": "block",
    },
    {
        "name": "PII Leak Prevention",
        "description": "Detects personally identifiable information such as email addresses, phone numbers, and SSN patterns in output.",
        "condition": {
            "type": "pattern",
            "pattern": r"(\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b|\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b|\b\(\d{3}\)\s*\d{3}[-.\s]?\d{4}\b)",
            "severity": "high",
        },
        "action": "warn",
    },
    {
        "name": "Cost Threshold Alert",
        "description": "Triggers when a single request cost exceeds $1.00, indicating unusually expensive operations.",
        "condition": {
            "type": "cost",
            "pattern": "cost_usd > 1.00",
            "severity": "high",
        },
        "action": "warn",
    },
    {
        "name": "Rate Anomaly Detection",
        "description": "Triggers when an agent makes more than 100 requests within a 5-minute window.",
        "condition": {
            "type": "rate",
            "pattern": "requests > 100 per 5m",
            "severity": "high",
        },
        "action": "warn",
    },
    {
        "name": "Toxic Content Filter",
        "description": "Detects profanity, hate speech indicators, and toxic language patterns.",
        "condition": {
            "type": "pattern",
            "pattern": r"(?i)(\bkill\s+(?:yourself|all)\b|\bhate\s+(?:speech|group)\b|\bracist\b|\bslur\b|\bthreat(?:en)?\b)",
            "severity": "critical",
        },
        "action": "block",
    },
    {
        "name": "Shell Command Blocking",
        "description": "Blocks dangerous shell commands including rm -rf, sudo, chmod 777, mkfs, and dd.",
        "condition": {
            "type": "pattern",
            "pattern": r"(?i)(\brm\s+-rf\b|\bsudo\b|\bchmod\s+777\b|\bmkfs\b|\bdd\s+if=|\b:\(\)\s*\{\s*:\|:\s*&\s*\})",
            "severity": "critical",
        },
        "action": "block",
    },
    {
        "name": "API Key Exposure",
        "description": "Detects leaked API keys from common providers (OpenAI, AWS, Google, GitHub, Stripe).",
        "condition": {
            "type": "pattern",
            "pattern": r"(sk-[a-zA-Z0-9]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|ghp_[a-zA-Z0-9]{36}|sk_live_[a-zA-Z0-9]{24,})",
            "severity": "critical",
        },
        "action": "block",
    },
]


async def seed_default_rules(session: AsyncSession) -> int:
    """Insert default rules if no built-in rules exist yet.

    Returns the number of rules seeded. Returns 0 if rules already exist.
    """
    stmt = select(func.count()).select_from(AuditRule).where(AuditRule.built_in.is_(True))
    result = await session.execute(stmt)
    existing_count = result.scalar_one()

    if existing_count > 0:
        logger.info("seed_rules_skipped", existing_built_in_count=existing_count)
        return 0

    seeded = 0
    for rule_data in DEFAULT_RULES:
        rule = AuditRule(
            name=rule_data["name"],
            description=rule_data["description"],
            condition=rule_data["condition"],
            action=rule_data["action"],
            enabled=True,
            built_in=True,
        )
        session.add(rule)
        seeded += 1

    await session.commit()
    logger.info("seed_rules_completed", rules_seeded=seeded)
    return seeded
