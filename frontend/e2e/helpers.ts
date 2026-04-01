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

export const mockSettings = {
  connections: {
    bsnexus_url: "https://nexus.bsvibe.dev",
    bsnexus_api_key: "sk-test-key-123",
    bsgateway_url: "https://gateway.bsvibe.dev",
    bsage_url: "",
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
