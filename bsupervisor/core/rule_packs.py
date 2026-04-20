"""Pre-built rule template packs organized by industry and framework."""

RULE_PACKS: list[dict] = [
    {
        "id": "healthcare-hipaa",
        "name": "Healthcare HIPAA Pack",
        "description": "Rules for HIPAA compliance: PII detection, patient data access controls, and PHI leak prevention.",
        "category": "healthcare",
        "rules": [
            {
                "name": "HIPAA: PHI in Output",
                "description": "Detects protected health information (medical record numbers, diagnosis codes) in agent output.",
                "condition": {
                    "type": "pattern",
                    "pattern": r"(?i)(\bMRN\s*[:=#]\s*\d+|\bICD[-.]?10\s*[:=#]|\bdiagnosis\s*:\s*\w+|\bpatient\s+name\s*:)",
                    "severity": "critical",
                },
                "action": "block",
            },
            {
                "name": "HIPAA: SSN Exposure",
                "description": "Blocks output containing Social Security Number patterns.",
                "condition": {
                    "type": "pattern",
                    "pattern": r"\b\d{3}-\d{2}-\d{4}\b",
                    "severity": "critical",
                },
                "action": "block",
            },
            {
                "name": "HIPAA: Medical Record Access",
                "description": "Warns when agents access medical record databases or FHIR endpoints.",
                "condition": {
                    "type": "pattern",
                    "pattern": r"(?i)(\bfhir\b|/Patient/|/Observation/|medical[_-]?records?|ehr[_-]?api)",
                    "severity": "high",
                },
                "action": "warn",
            },
            {
                "name": "HIPAA: Data Export Warning",
                "description": "Warns when agents attempt bulk data export from health systems.",
                "condition": {
                    "type": "pattern",
                    "pattern": r"(?i)(\bbulk[_-]?export|\$export|/Group/.*\$export)",
                    "severity": "high",
                },
                "action": "warn",
            },
        ],
    },
    {
        "id": "financial-compliance",
        "name": "Financial Compliance Pack",
        "description": "Rules for financial services: transaction monitoring, credit card detection, and regulatory controls.",
        "category": "finance",
        "rules": [
            {
                "name": "Finance: Credit Card Number",
                "description": "Blocks output containing credit card number patterns (Visa, Mastercard, Amex).",
                "condition": {
                    "type": "pattern",
                    "pattern": r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b",
                    "severity": "critical",
                },
                "action": "block",
            },
            {
                "name": "Finance: IBAN Exposure",
                "description": "Detects International Bank Account Numbers in agent output.",
                "condition": {
                    "type": "pattern",
                    "pattern": r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b",
                    "severity": "critical",
                },
                "action": "block",
            },
            {
                "name": "Finance: Large Transaction Alert",
                "description": "Warns on transaction amounts exceeding $10,000 (AML reporting threshold).",
                "condition": {
                    "type": "pattern",
                    "pattern": r"(?i)(\btransaction|\btransfer|\bpayment).*\$\s*(?:[1-9]\d{4,}|[1-9]\d{1,2},\d{3})",
                    "severity": "high",
                },
                "action": "warn",
            },
            {
                "name": "Finance: Trading API Access",
                "description": "Warns when agents interact with trading or brokerage APIs.",
                "condition": {
                    "type": "pattern",
                    "pattern": r"(?i)(/api/v\d+/orders|/trades|/positions|place[_-]?order|execute[_-]?trade)",
                    "severity": "high",
                },
                "action": "warn",
            },
        ],
    },
    {
        "id": "langchain-agent",
        "name": "LangChain Agent Pack",
        "description": "Safety rules for LangChain-based agents: tool call validation, chain depth limits, and output sanitization.",
        "category": "ai-framework",
        "rules": [
            {
                "name": "LangChain: Recursive Chain Depth",
                "description": "Warns when chain recursion depth indicators suggest runaway loops.",
                "condition": {
                    "type": "pattern",
                    "pattern": r"(?i)(recursion[_-]?depth|max[_-]?iterations?\s*exceeded|chain[_-]?depth\s*>\s*\d{2,})",
                    "severity": "high",
                },
                "action": "warn",
            },
            {
                "name": "LangChain: Unauthorized Tool Call",
                "description": "Blocks tool calls to shell, file system, or network tools not in the allowlist.",
                "condition": {
                    "type": "pattern",
                    "pattern": r"(?i)(ShellTool|BashProcess|FileSystem(?:Read|Write|Delete)|RequestsGet|RequestsPost)",
                    "severity": "critical",
                },
                "action": "block",
            },
            {
                "name": "LangChain: Prompt Leakage",
                "description": "Detects when system prompts or internal instructions appear in agent output.",
                "condition": {
                    "type": "pattern",
                    "pattern": r"(?i)(system\s*prompt\s*:|internal\s*instructions?\s*:|<<\s*system\s*>>|you\s+are\s+a\s+helpful\s+assistant)",
                    "severity": "high",
                },
                "action": "warn",
            },
            {
                "name": "LangChain: Token Budget Exceeded",
                "description": "Warns when token usage indicators suggest a single chain is consuming excessive tokens.",
                "condition": {
                    "type": "pattern",
                    "pattern": r"(?i)(total[_-]?tokens?\s*[:=]\s*\d{5,}|token[_-]?budget\s*exceeded)",
                    "severity": "medium",
                },
                "action": "warn",
            },
        ],
    },
]


def list_packs() -> list[dict]:
    """Return summary list of all available packs (without full rule details)."""
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "description": p["description"],
            "category": p["category"],
            "rule_count": len(p["rules"]),
        }
        for p in RULE_PACKS
    ]


def get_pack(pack_id: str) -> dict | None:
    """Return a full pack definition including rules, or None if not found."""
    for p in RULE_PACKS:
        if p["id"] == pack_id:
            return {
                "id": p["id"],
                "name": p["name"],
                "description": p["description"],
                "category": p["category"],
                "rule_count": len(p["rules"]),
                "rules": p["rules"],
            }
    return None
