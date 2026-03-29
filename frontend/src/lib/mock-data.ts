import type {
  StatusMetrics,
  Event,
  Rule,
  DailyReportData,
  CostData,
} from "./api";

export const mockStatus: StatusMetrics = {
  events_today: 1247,
  violations: 23,
  blocked_actions: 8,
  cost_total: "$142.38",
};

const now = Date.now();
const hours = Array.from({ length: 24 }, (_, i) => {
  const d = new Date(now - (23 - i) * 3600000);
  return d.toISOString().slice(0, 13) + ":00";
});

export const mockTimelineData = hours.map((hour) => ({
  hour: hour.slice(11, 16),
  safe: Math.floor(Math.random() * 40 + 20),
  warning: Math.floor(Math.random() * 8 + 1),
  blocked: Math.floor(Math.random() * 3),
}));

const severities: Event["severity"][] = ["safe", "warning", "blocked"];
const actions = [
  "file_write",
  "api_call",
  "shell_exec",
  "db_query",
  "network_request",
  "config_change",
];
const agents = ["agent-alpha", "agent-beta", "agent-gamma", "agent-delta"];

export const mockEvents: Event[] = Array.from({ length: 50 }, (_, i) => {
  const severity = severities[i < 5 ? 2 : i < 15 ? 1 : 0];
  return {
    id: `evt-${1000 + i}`,
    timestamp: new Date(now - i * 120000).toISOString(),
    agent_id: agents[i % agents.length],
    action: actions[i % actions.length],
    severity,
    rule_name:
      severity !== "safe" ? `rule-${Math.floor(Math.random() * 10)}` : undefined,
    details:
      severity === "blocked"
        ? "Action blocked by safety rule"
        : severity === "warning"
          ? "Unusual pattern detected"
          : undefined,
  };
});

export const mockRules: Rule[] = [
  {
    id: "rule-1",
    name: "Block Shell Exec",
    type: "action",
    pattern: "shell_exec.*rm -rf",
    severity: "critical",
    action: "block",
    description: "Prevents destructive shell commands",
    enabled: true,
    built_in: true,
    hit_count: 42,
  },
  {
    id: "rule-2",
    name: "Rate Limit API",
    type: "rate",
    pattern: "api_call > 100/min",
    severity: "high",
    action: "block",
    description: "Rate limit external API calls",
    enabled: true,
    built_in: true,
    hit_count: 156,
  },
  {
    id: "rule-3",
    name: "Sensitive File Guard",
    type: "pattern",
    pattern: "file_write.*/etc/.*|.*\\.env.*",
    severity: "critical",
    action: "block",
    description: "Block writes to sensitive files",
    enabled: true,
    built_in: true,
    hit_count: 18,
  },
  {
    id: "rule-4",
    name: "Cost Threshold",
    type: "cost",
    pattern: "daily_cost > 50.00",
    severity: "high",
    action: "warn",
    description: "Alert when daily cost exceeds threshold",
    enabled: true,
    built_in: false,
    hit_count: 7,
  },
  {
    id: "rule-5",
    name: "Unusual Network",
    type: "pattern",
    pattern: "network_request.*internal.*",
    severity: "medium",
    action: "warn",
    description: "Flag internal network access",
    enabled: false,
    built_in: false,
    hit_count: 0,
  },
  {
    id: "rule-6",
    name: "DB Write Audit",
    type: "action",
    pattern: "db_query.*(INSERT|UPDATE|DELETE)",
    severity: "medium",
    action: "log",
    description: "Log all database write operations",
    enabled: true,
    built_in: false,
    hit_count: 312,
  },
];

export const mockTopRules = [
  { name: "DB Write Audit", hits: 312, severity: "medium" },
  { name: "Rate Limit API", hits: 156, severity: "high" },
  { name: "Block Shell Exec", hits: 42, severity: "critical" },
  { name: "Sensitive File Guard", hits: 18, severity: "critical" },
  { name: "Cost Threshold", hits: 7, severity: "high" },
];

export const mockDailyReport: DailyReportData = {
  date: new Date().toISOString().slice(0, 10),
  markdown: `# Daily Safety Report

## Executive Summary

BSupervisor monitored **1,247 events** across 4 active agents today. **23 violations** were detected and **8 actions** were blocked. Overall safety posture is **good** with no critical incidents requiring escalation.

## Event Breakdown

| Category | Count | Change |
|----------|-------|--------|
| Total Events | 1,247 | +12% |
| Safe | 1,216 | +14% |
| Warnings | 23 | -8% |
| Blocked | 8 | -25% |

Most events were routine \`file_write\` and \`api_call\` operations from agent-alpha and agent-beta.

## Violations

### Critical (0)
No critical violations today.

### High (3)
- **Rate Limit API** triggered 3 times by agent-beta between 14:00-14:30 UTC
- All instances were automatically blocked

### Medium (20)
- **DB Write Audit** logged 20 database modifications
- All were within expected patterns

## Cost Summary

| Agent | Requests | Cost |
|-------|----------|------|
| agent-alpha | 523 | $62.14 |
| agent-beta | 412 | $48.92 |
| agent-gamma | 198 | $22.08 |
| agent-delta | 114 | $9.24 |
| **Total** | **1,247** | **$142.38** |

Budget utilization: **71.2%** of daily budget ($200.00)
`,
};

export const mockCosts: CostData = {
  budget: "$200.00",
  spent: "$142.38",
  budget_percentage: 71.2,
  trend: Array.from({ length: 30 }, (_, i) => {
    const d = new Date(now - (29 - i) * 86400000);
    return {
      date: d.toISOString().slice(0, 10),
      cost: Math.round((Math.random() * 80 + 100) * 100) / 100,
    };
  }),
  agents: [
    {
      agent_id: "agent-alpha",
      agent_name: "Agent Alpha",
      requests: 523,
      tokens: 1240000,
      cost: "$62.14",
      percentage: 43.6,
      daily_costs: Array.from({ length: 7 }, () =>
        Math.round(Math.random() * 20 + 50),
      ),
    },
    {
      agent_id: "agent-beta",
      agent_name: "Agent Beta",
      requests: 412,
      tokens: 980000,
      cost: "$48.92",
      percentage: 34.4,
      daily_costs: Array.from({ length: 7 }, () =>
        Math.round(Math.random() * 15 + 40),
      ),
    },
    {
      agent_id: "agent-gamma",
      agent_name: "Agent Gamma",
      requests: 198,
      tokens: 440000,
      cost: "$22.08",
      percentage: 15.5,
      daily_costs: Array.from({ length: 7 }, () =>
        Math.round(Math.random() * 10 + 15),
      ),
    },
    {
      agent_id: "agent-delta",
      agent_name: "Agent Delta",
      requests: 114,
      tokens: 185000,
      cost: "$9.24",
      percentage: 6.5,
      daily_costs: Array.from({ length: 7 }, () =>
        Math.round(Math.random() * 5 + 5),
      ),
    },
  ],
  anomalies: ["agent-beta"],
};
