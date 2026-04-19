import type { Page } from "@playwright/test";

/** Inject fake auth tokens into localStorage so ProtectedRoute lets us through. */
export async function injectAuth(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("bsupervisor_token", "fake-jwt-token");
    localStorage.setItem(
      "bsupervisor_user",
      JSON.stringify({ email: "test@example.com", name: "Test User" }),
    );
  });
}

// ---- Mock API data ----

export const mockStatus = {
  events_today: 142,
  violations: 3,
  blocked_actions: 2,
  cost_total: "$48.23",
};

export const mockEvents = [
  {
    id: "evt-1",
    timestamp: new Date().toISOString(),
    agent_id: "agent-alpha",
    action: "file_write /etc/passwd",
    severity: "blocked",
    rule_name: "System File Protection",
  },
  {
    id: "evt-2",
    timestamp: new Date().toISOString(),
    agent_id: "agent-beta",
    action: "api_call https://external.io",
    severity: "warning",
    rule_name: "External API Monitor",
  },
  {
    id: "evt-3",
    timestamp: new Date().toISOString(),
    agent_id: "agent-gamma",
    action: "read_file config.yaml",
    severity: "safe",
  },
];

export const mockRules = [
  {
    id: "rule-1",
    name: "System File Protection",
    type: "pattern",
    pattern: "/etc/*",
    severity: "critical",
    action: "block",
    description: "Block access to system files",
    enabled: true,
    built_in: true,
    hit_count: 87,
  },
  {
    id: "rule-2",
    name: "External API Monitor",
    type: "action",
    pattern: "api_call external*",
    severity: "high",
    action: "warn",
    description: "Warn on external API calls",
    enabled: true,
    built_in: false,
    hit_count: 42,
  },
  {
    id: "rule-3",
    name: "Cost Threshold",
    type: "cost",
    pattern: ">100",
    severity: "medium",
    action: "warn",
    description: "Warn when cost exceeds threshold",
    enabled: false,
    built_in: false,
    hit_count: 5,
  },
];

export const mockDailyReport = {
  date: new Date().toISOString().slice(0, 10),
  markdown:
    "# Daily Safety Report\n\n## Summary\n\n**3 violations** detected across 142 events.\n\n## Top Issues\n\n- System file access attempt by agent-alpha\n- Unusual external API call patterns\n\n## Recommendations\n\n- Review agent-alpha permissions\n- Update rate limiting rules",
};

export const mockCosts = {
  budget: "$100.00",
  spent: "$48.23",
  budget_percentage: 48.23,
  trend: Array.from({ length: 30 }, (_, i) => ({
    date: `2026-03-${String(i + 1).padStart(2, "0")}`,
    cost: 30 + Math.random() * 40,
  })),
  agents: [
    {
      agent_id: "agent-alpha",
      agent_name: "Alpha Assistant",
      requests: 1250,
      tokens: 450000,
      cost: "$22.50",
      percentage: 46.7,
      daily_costs: [3, 4, 3, 5, 2, 3, 4],
    },
    {
      agent_id: "agent-beta",
      agent_name: "Beta Processor",
      requests: 800,
      tokens: 280000,
      cost: "$14.00",
      percentage: 29.0,
      daily_costs: [2, 2, 3, 2, 2, 3, 2],
    },
    {
      agent_id: "agent-gamma",
      agent_name: "Gamma Worker",
      requests: 500,
      tokens: 180000,
      cost: "$11.73",
      percentage: 24.3,
      daily_costs: [1, 2, 1, 2, 1, 2, 3],
    },
  ],
  anomalies: ["agent-alpha"],
};

export const mockIncidents = [
  {
    id: "inc-1",
    agent_id: "agent-alpha",
    title: "Blocked file_delete: /secrets/private.key",
    status: "open",
    severity: "critical",
    event_count: 3,
    started_at: new Date(Date.now() - 3600000).toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "inc-2",
    agent_id: "agent-beta",
    title: "Blocked shell_exec: sudo rm -rf /",
    status: "resolved",
    severity: "critical",
    event_count: 1,
    started_at: new Date(Date.now() - 7200000).toISOString(),
    updated_at: new Date(Date.now() - 7000000).toISOString(),
  },
];

export const mockIncidentDetail = {
  ...mockIncidents[0],
  timeline: [
    {
      id: "tl-1",
      timestamp: new Date(Date.now() - 3600000).toISOString(),
      event_type: "file_access",
      action: "read",
      target: "/secrets/private.key",
      allowed: true,
    },
    {
      id: "tl-2",
      timestamp: new Date(Date.now() - 1800000).toISOString(),
      event_type: "file_delete",
      action: "delete",
      target: "/secrets/private.key",
      allowed: false,
    },
    {
      id: "tl-3",
      timestamp: new Date(Date.now() - 600000).toISOString(),
      event_type: "file_delete",
      action: "delete",
      target: "/app/.env",
      allowed: false,
    },
  ],
};

export const mockRulePacks = [
  {
    id: "healthcare-hipaa",
    name: "Healthcare HIPAA Pack",
    description: "Rules for HIPAA compliance.",
    category: "healthcare",
    rule_count: 4,
  },
  {
    id: "financial-compliance",
    name: "Financial Compliance Pack",
    description: "Rules for financial services.",
    category: "finance",
    rule_count: 4,
  },
  {
    id: "langchain-agent",
    name: "LangChain Agent Pack",
    description: "Safety rules for LangChain-based agents.",
    category: "ai-framework",
    rule_count: 4,
  },
];

export const mockAnomalies = [
  {
    agent_id: "agent-alpha",
    metric: "cost",
    current_value: "45.00",
    baseline_mean: "10.00",
    baseline_stddev: "2.00",
    multiplier: 3.5,
    is_anomaly: true,
  },
];

export const mockEventsWithExplanation = [
  {
    id: "evt-1",
    timestamp: new Date().toISOString(),
    agent_id: "agent-alpha",
    action: "file_write /etc/passwd",
    severity: "blocked",
    rule_name: "System File Protection",
    explanation: {
      rule_name: "builtin:block_sensitive_file_delete",
      rule_description: "Blocks deletion of sensitive credential files",
      rule_type: "builtin",
      matched_field: "target",
      matched_value: "/etc/passwd",
      matched_pattern: ".env",
      severity: "critical",
      suggestion: "Use a secrets manager instead",
    },
  },
  {
    id: "evt-2",
    timestamp: new Date().toISOString(),
    agent_id: "agent-beta",
    action: "api_call https://external.io",
    severity: "warning",
    rule_name: "External API Monitor",
  },
  {
    id: "evt-3",
    timestamp: new Date().toISOString(),
    agent_id: "agent-gamma",
    action: "read_file config.yaml",
    severity: "safe",
  },
];

export const mockSettings = {
  connections: {
    integrations: [
      {
        id: "int-1",
        name: "BSNexus",
        type: "bsnexus",
        endpoint_url: "https://nexus.bsvibe.dev",
        api_key: "sk-test-key-123",
      },
      {
        id: "int-2",
        name: "BSGateway",
        type: "bsgateway",
        endpoint_url: "https://gateway.bsvibe.dev",
        api_key: "",
      },
    ],
    telegram_bot_token: "",
    slack_webhook_url: "",
  },
};

/** Set up page.route() mocks for all API endpoints. */
export async function mockAllApis(page: Page) {
  await page.route("**/api/status", (route) =>
    route.fulfill({ json: mockStatus }),
  );
  await page.route("**/api/events", (route) =>
    route.fulfill({ json: mockEvents }),
  );
  await page.route("**/api/rules", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: mockRules });
    }
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      return route.fulfill({
        json: {
          id: "rule-new",
          ...body,
          enabled: true,
          built_in: false,
          hit_count: 0,
        },
      });
    }
    return route.fulfill({ status: 200 });
  });
  await page.route("**/api/rules/*", (route) => {
    if (route.request().method() === "PUT") {
      return route.fulfill({
        json: { ...mockRules[1], ...route.request().postDataJSON() },
      });
    }
    if (route.request().method() === "DELETE") {
      return route.fulfill({ status: 204 });
    }
    return route.fulfill({ status: 200 });
  });
  await page.route("**/api/reports/daily*", (route) =>
    route.fulfill({ json: mockDailyReport }),
  );
  await page.route("**/api/costs", (route) =>
    route.fulfill({ json: mockCosts }),
  );
  await page.route("**/api/incidents/*", (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({ json: { id: "inc-1", status: "resolved" } });
    }
    return route.fulfill({ json: mockIncidentDetail });
  });
  await page.route("**/api/incidents", (route) =>
    route.fulfill({ json: mockIncidents }),
  );
  await page.route("**/api/rule-packs/*/install", (route) =>
    route.fulfill({ json: { pack_id: "healthcare-hipaa", installed: 4, skipped: 0 } }),
  );
  await page.route("**/api/rule-packs/*", (route) =>
    route.fulfill({
      json: {
        ...mockRulePacks[0],
        rules: [
          { name: "HIPAA: PHI in Output", description: "Detects PHI", action: "block" },
          { name: "HIPAA: SSN Exposure", description: "Blocks SSN", action: "block" },
        ],
      },
    }),
  );
  await page.route("**/api/rule-packs", (route) =>
    route.fulfill({ json: mockRulePacks }),
  );
  await page.route("**/api/anomalies", (route) =>
    route.fulfill({ json: mockAnomalies }),
  );
  await page.route("**/api/settings", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: mockSettings });
    }
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON();
      return route.fulfill({ json: { connections: body } });
    }
    return route.fulfill({ status: 200 });
  });
}
