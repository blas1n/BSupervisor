import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
});

// Attach auth token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("bsupervisor_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 by clearing auth and redirecting to login
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("bsupervisor_token");
      localStorage.removeItem("bsupervisor_user");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  },
);

// --- Types ---

export interface StatusMetrics {
  events_today: number;
  violations: number;
  blocked_actions: number;
  cost_total: string;
}

export interface Event {
  id: string;
  timestamp: string;
  agent_id: string;
  action: string;
  severity: "safe" | "warning" | "blocked";
  rule_name?: string;
  details?: string;
}

export interface Rule {
  id: string;
  name: string;
  type: string;
  pattern: string;
  severity: string;
  action: string;
  description?: string;
  enabled: boolean;
  built_in: boolean;
  hit_count: number;
}

export interface RuleCreate {
  name: string;
  type: string;
  pattern: string;
  severity: string;
  action: string;
  description?: string;
}

export interface DailyReportData {
  date: string;
  markdown: string;
}

export interface CostEntry {
  agent_id: string;
  agent_name: string;
  requests: number;
  tokens: number;
  cost: string;
  percentage: number;
  daily_costs: number[];
}

export interface CostData {
  budget: string;
  spent: string;
  budget_percentage: number;
  trend: { date: string; cost: number }[];
  agents: CostEntry[];
  anomalies: string[];
}

// --- API calls ---

export async function fetchStatus(): Promise<StatusMetrics> {
  const { data } = await api.get("/status");
  return data;
}

export async function fetchEvents(): Promise<Event[]> {
  const { data } = await api.get("/events");
  return data;
}

export async function fetchRules(): Promise<Rule[]> {
  const { data } = await api.get("/rules");
  return data;
}

export async function createRule(rule: RuleCreate): Promise<Rule> {
  const { data } = await api.post("/rules", rule);
  return data;
}

export async function updateRule(
  id: string,
  rule: Partial<RuleCreate> & { enabled?: boolean },
): Promise<Rule> {
  const { data } = await api.put(`/rules/${id}`, rule);
  return data;
}

export async function deleteRule(id: string): Promise<void> {
  await api.delete(`/rules/${id}`);
}

export async function fetchDailyReport(
  date: string,
): Promise<DailyReportData> {
  const { data } = await api.get(`/reports/daily?date=${date}`);
  return data;
}

export async function fetchCosts(): Promise<CostData> {
  const { data } = await api.get("/costs");
  return data;
}
