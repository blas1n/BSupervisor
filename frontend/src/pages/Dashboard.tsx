import { useState, useEffect, useMemo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import {
  Activity,
  AlertTriangle,
  ShieldOff,
  DollarSign,
  ShieldAlert,
  ShieldCheck,
  CircleDot,
  Clock,
  Loader2,
} from "lucide-react";
import { StatCard } from "../components/StatCard";
import { SeverityBadge } from "../components/SeverityBadge";
import { formatNumber, formatTime, eventSeverityColor, cn } from "../lib/utils";
import { theme } from "../lib/theme";
import {
  fetchStatus,
  fetchEvents,
  fetchRules,
} from "../lib/api";
import type { StatusMetrics, Event, Rule } from "../lib/api";

function SeverityIcon({ severity }: { severity: string }) {
  const color = eventSeverityColor(severity);
  switch (severity) {
    case "blocked":
      return <ShieldOff className={cn("h-4 w-4", color)} />;
    case "warning":
      return <AlertTriangle className={cn("h-4 w-4", color)} />;
    default:
      return <ShieldCheck className={cn("h-4 w-4", color)} />;
  }
}

function buildTimelineData(events: Event[]) {
  const buckets: Record<string, { safe: number; warning: number; blocked: number }> = {};
  const now = new Date();
  for (let i = 23; i >= 0; i--) {
    const d = new Date(now.getTime() - i * 3600000);
    const hour = `${String(d.getHours()).padStart(2, "0")}:00`;
    buckets[hour] = { safe: 0, warning: 0, blocked: 0 };
  }
  for (const event of events) {
    const d = new Date(event.timestamp);
    const hour = `${String(d.getHours()).padStart(2, "0")}:00`;
    if (buckets[hour]) {
      buckets[hour][event.severity]++;
    }
  }
  return Object.entries(buckets).map(([hour, counts]) => ({ hour, ...counts }));
}

function buildTopRules(rules: Rule[]) {
  return [...rules]
    .sort((a, b) => b.hit_count - a.hit_count)
    .slice(0, 5)
    .map((r) => ({ name: r.name, hits: r.hit_count, severity: r.severity }));
}

export function Dashboard() {
  const [status, setStatus] = useState<StatusMetrics | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [s, e, r] = await Promise.all([fetchStatus(), fetchEvents(), fetchRules()]);
        setStatus(s);
        setEvents(e);
        setRules(r);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load dashboard data");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const timelineData = useMemo(() => buildTimelineData(events), [events]);
  const topRules = useMemo(() => buildTopRules(rules), [rules]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-gray-500" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-accent/30 bg-accent/10 px-4 py-8 text-center text-sm text-accent">
        {error}
      </div>
    );
  }

  if (!status) return null;

  const hasCriticalViolations = status.violations > 0;

  return (
    <div className="space-y-6">
      {/* Critical alert banner */}
      {hasCriticalViolations && (
        <div className="flex items-center gap-3 rounded-lg border border-accent/30 bg-accent/10 px-4 py-3">
          <ShieldAlert className="h-5 w-5 flex-shrink-0 text-accent" />
          <div className="flex-1">
            <p className="text-sm font-medium text-accent">
              {status.violations} violation{status.violations !== 1 && "s"}{" "}
              detected today &mdash; {status.blocked_actions} action
              {status.blocked_actions !== 1 && "s"} blocked
            </p>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-accent/70">
            <Clock className="h-3 w-3" />
            <span>Live</span>
          </div>
        </div>
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Events Today"
          value={formatNumber(status.events_today)}
          icon={Activity}
        />
        <StatCard
          label="Violations"
          value={formatNumber(status.violations)}
          icon={AlertTriangle}
          accent
        />
        <StatCard
          label="Blocked"
          value={formatNumber(status.blocked_actions)}
          icon={ShieldOff}
          accent
        />
        <StatCard
          label="Cost"
          value={status.cost_total}
          icon={DollarSign}
        />
      </div>

      {/* Charts + Feed */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* 24h stacked area chart */}
        <div className="col-span-2 rounded-lg border border-gray-800 bg-gray-900 p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-300">
              24h Event Timeline
            </h2>
            <div className="flex items-center gap-4 text-[11px] text-gray-500">
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2 w-2 rounded-full bg-success" />
                Safe
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2 w-2 rounded-full bg-warning" />
                Warning
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2 w-2 rounded-full bg-accent" />
                Blocked
              </span>
            </div>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={timelineData}>
                <defs>
                  <linearGradient id="gradSafe" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={theme.success} stopOpacity={0.4} />
                    <stop offset="100%" stopColor={theme.success} stopOpacity={0.05} />
                  </linearGradient>
                  <linearGradient id="gradWarn" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={theme.warning} stopOpacity={0.4} />
                    <stop offset="100%" stopColor={theme.warning} stopOpacity={0.05} />
                  </linearGradient>
                  <linearGradient id="gradBlocked" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={theme.accent} stopOpacity={0.4} />
                    <stop offset="100%" stopColor={theme.accent} stopOpacity={0.05} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="hour"
                  tick={{ fontSize: 11, fill: theme.gray400 }}
                  interval={3}
                />
                <YAxis tick={{ fontSize: 11, fill: theme.gray400 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: theme.gray800,
                    border: `1px solid ${theme.gray700}`,
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  itemStyle={{ color: theme.gray100 }}
                  labelStyle={{ color: theme.gray300 }}
                />
                <Area
                  type="monotone"
                  dataKey="safe"
                  stackId="1"
                  stroke={theme.success}
                  fill="url(#gradSafe)"
                  strokeWidth={1.5}
                />
                <Area
                  type="monotone"
                  dataKey="warning"
                  stackId="1"
                  stroke={theme.warning}
                  fill="url(#gradWarn)"
                  strokeWidth={1.5}
                />
                <Area
                  type="monotone"
                  dataKey="blocked"
                  stackId="1"
                  stroke={theme.accent}
                  fill="url(#gradBlocked)"
                  strokeWidth={1.5}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Live event feed */}
        <div className="rounded-lg border border-gray-800 bg-gray-900 p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-300">
              Live Event Feed
            </h2>
            <span className="flex items-center gap-1.5 text-[10px] font-medium text-success-light">
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-success-light" />
              Live
            </span>
          </div>
          <div className="h-64 space-y-0.5 overflow-y-auto pr-1">
            {events.length === 0 ? (
              <p className="py-8 text-center text-sm text-gray-500">No events yet</p>
            ) : (
              events.slice(0, 20).map((event) => (
                <div
                  key={event.id}
                  className="flex items-start gap-2.5 rounded-md px-2.5 py-2 transition-colors hover:bg-gray-850"
                >
                  <SeverityIcon severity={event.severity} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate text-xs font-medium text-gray-100">
                        {event.action}
                      </p>
                      <span className="flex-shrink-0 font-mono text-[10px] text-gray-500">
                        {formatTime(event.timestamp)}
                      </span>
                    </div>
                    <p className="truncate text-[11px] text-gray-500">
                      {event.agent_id}
                      {event.rule_name && (
                        <span className="text-gray-600">
                          {" "}
                          &middot; {event.rule_name}
                        </span>
                      )}
                    </p>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Top triggered rules */}
      <div className="rounded-lg border border-gray-800 bg-gray-900 p-5">
        <h2 className="mb-4 text-sm font-semibold text-gray-300">
          Top Triggered Rules
        </h2>
        {topRules.length === 0 ? (
          <p className="py-4 text-center text-sm text-gray-500">No rules configured</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-left text-xs font-medium text-gray-500">
                <th className="pb-3 pr-4">Rule</th>
                <th className="pb-3 pr-4">Severity</th>
                <th className="pb-3 text-right">Hits</th>
              </tr>
            </thead>
            <tbody>
              {topRules.map((rule) => (
                <tr
                  key={rule.name}
                  className="border-b border-gray-800/50 last:border-0"
                >
                  <td className="py-3 pr-4 font-medium text-gray-100">
                    <div className="flex items-center gap-2">
                      <CircleDot className="h-3.5 w-3.5 text-gray-500" />
                      {rule.name}
                    </div>
                  </td>
                  <td className="py-3 pr-4">
                    <SeverityBadge severity={rule.severity} />
                  </td>
                  <td className="py-3 text-right font-mono text-gray-300">
                    {formatNumber(rule.hits)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
