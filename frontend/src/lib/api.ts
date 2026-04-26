/**
 * BSupervisor API client — Phase A consumer of `@bsvibe/api`.
 *
 * The shared `createApiFetch` replaces the legacy axios instance + 401
 * interceptor + bearer-token attachment with a single fetch-based client.
 * `setOnAuthError` registers the global cascading-logout latch so multiple
 * concurrent 401s only redirect once.
 *
 * Public types (`Event`, `Rule`, `CostData`, etc.) are unchanged so the
 * existing component tree keeps compiling.
 */

import { createApiFetch, readDualEnv, setOnAuthError } from "@bsvibe/api";
import { getAccessToken } from "../hooks/useAuth";

const AUTH_URL =
  process.env.NEXT_PUBLIC_BSVIBE_AUTH_URL ?? "https://auth.bsvibe.dev";

// `readDualEnv` honours both Next.js (`NEXT_PUBLIC_*`) and legacy Vite
// (`VITE_*`) env vars so the same client compiles in either bundler.
const BASE_URL = readDualEnv("API_URL", { fallback: "/api" }) ?? "/api";

// Register the 401 cascading-logout latch exactly once per page load.
// Subsequent 401s are absorbed by the shared guard until the latch is reset.
if (typeof window !== "undefined") {
  setOnAuthError(() => {
    window.location.href = `${AUTH_URL}/login`;
  });
}

const api = createApiFetch({
  baseUrl: BASE_URL,
  getToken: () => getAccessToken(),
  onUnauthorized: () => {
    if (typeof window !== "undefined") {
      window.location.href = `${AUTH_URL}/login`;
    }
  },
});

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
  return api.get<StatusMetrics>("/status");
}

export async function fetchEvents(): Promise<Event[]> {
  return api.get<Event[]>("/events");
}

export async function fetchRules(): Promise<Rule[]> {
  return api.get<Rule[]>("/rules");
}

export async function createRule(rule: RuleCreate): Promise<Rule> {
  return api.post<Rule>("/rules", rule);
}

export async function updateRule(
  id: string,
  rule: Partial<RuleCreate> & { enabled?: boolean },
): Promise<Rule> {
  return api.put<Rule>(`/rules/${id}`, rule);
}

export async function deleteRule(id: string): Promise<void> {
  await api.delete(`/rules/${id}`);
}

export async function fetchDailyReport(
  date: string,
): Promise<DailyReportData> {
  return api.get<DailyReportData>(`/reports/daily?date=${date}`);
}

export async function fetchCosts(): Promise<CostData> {
  return api.get<CostData>("/costs");
}

export async function fetchSettings(): Promise<SettingsData> {
  return api.get<SettingsData>("/settings");
}

export async function updateSettings(
  connections: ConnectionSettings,
): Promise<SettingsData> {
  return api.put<SettingsData>("/settings", connections);
}

// --- Incidents ---

export async function fetchIncidents(): Promise<IncidentListItem[]> {
  return api.get<IncidentListItem[]>("/incidents");
}

export async function fetchIncident(id: string): Promise<IncidentDetail> {
  return api.get<IncidentDetail>(`/incidents/${id}`);
}

export async function resolveIncident(id: string): Promise<{ id: string; status: string }> {
  return api.post<{ id: string; status: string }>(`/incidents/${id}/resolve`);
}

// --- Rule Packs ---

export async function fetchRulePacks(): Promise<RulePackSummary[]> {
  return api.get<RulePackSummary[]>("/rule-packs");
}

export async function fetchRulePack(id: string): Promise<RulePackDetail> {
  return api.get<RulePackDetail>(`/rule-packs/${id}`);
}

export async function installRulePack(id: string): Promise<InstallResult> {
  return api.post<InstallResult>(`/rule-packs/${id}/install`);
}

// --- Anomalies ---

export async function fetchAnomalies(): Promise<AnomalyEntry[]> {
  return api.get<AnomalyEntry[]>("/anomalies");
}
