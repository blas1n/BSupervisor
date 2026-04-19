import axios from "axios";
import { getToken } from "./auth";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "/api",
  headers: { "Content-Type": "application/json" },
});

// Attach auth token to every request
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 by redirecting to login
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      window.location.href = "/";
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
  explanation?: Explanation;
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

export type IntegrationType = "bsnexus" | "bsgateway" | "bsage" | "openai" | "anthropic" | "custom";

export interface IntegrationEntry {
  id: string;
  name: string;
  type: IntegrationType;
  endpoint_url: string;
  api_key: string;
}

export interface ConnectionSettings {
  integrations: IntegrationEntry[];
  telegram_bot_token: string;
  slack_webhook_url: string;
}

export interface SettingsData {
  connections: ConnectionSettings;
}

// --- Explainable Block ---

export interface Explanation {
  rule_name: string;
  rule_description: string;
  rule_type: string;
  matched_field: string;
  matched_value: string;
  matched_pattern: string;
  severity: string;
  suggestion?: string;
}

// --- Incidents ---

export interface IncidentListItem {
  id: string;
  agent_id: string;
  title: string;
  status: string;
  severity: string;
  event_count: number;
  started_at: string;
  updated_at: string;
}

export interface TimelineEntry {
  id: string;
  timestamp: string;
  event_type: string;
  action: string;
  target: string;
  allowed: boolean;
}

export interface IncidentDetail extends IncidentListItem {
  timeline: TimelineEntry[];
}

// --- Rule Packs ---

export interface RulePackSummary {
  id: string;
  name: string;
  description: string;
  category: string;
  rule_count: number;
}

export interface RulePackRule {
  name: string;
  description: string;
  action: string;
}

export interface RulePackDetail extends RulePackSummary {
  rules: RulePackRule[];
}

export interface InstallResult {
  pack_id: string;
  installed: number;
  skipped: number;
}

// --- Anomalies ---

export interface AnomalyEntry {
  agent_id: string;
  metric: string;
  current_value: string;
  baseline_mean: string;
  baseline_stddev: string;
  multiplier: number;
  is_anomaly: boolean;
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

export async function fetchSettings(): Promise<SettingsData> {
  const { data } = await api.get("/settings");
  return data;
}

export async function updateSettings(
  connections: ConnectionSettings,
): Promise<SettingsData> {
  const { data } = await api.put("/settings", connections);
  return data;
}

// --- Incidents ---

export async function fetchIncidents(): Promise<IncidentListItem[]> {
  const { data } = await api.get("/incidents");
  return data;
}

export async function fetchIncident(id: string): Promise<IncidentDetail> {
  const { data } = await api.get(`/incidents/${id}`);
  return data;
}

export async function resolveIncident(id: string): Promise<{ id: string; status: string }> {
  const { data } = await api.post(`/incidents/${id}/resolve`);
  return data;
}

// --- Rule Packs ---

export async function fetchRulePacks(): Promise<RulePackSummary[]> {
  const { data } = await api.get("/rule-packs");
  return data;
}

export async function fetchRulePack(id: string): Promise<RulePackDetail> {
  const { data } = await api.get(`/rule-packs/${id}`);
  return data;
}

export async function installRulePack(id: string): Promise<InstallResult> {
  const { data } = await api.post(`/rule-packs/${id}/install`);
  return data;
}

// --- Anomalies ---

export async function fetchAnomalies(): Promise<AnomalyEntry[]> {
  const { data } = await api.get("/anomalies");
  return data;
}
