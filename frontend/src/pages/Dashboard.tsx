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
import { formatNumber, formatTime, cn } from "../lib/utils";
import { theme } from "../lib/theme";
import { fetchStatus, fetchEvents, fetchRules } from "../lib/api";
import type { StatusMetrics, Event, Rule } from "../lib/api";
import { SeverityBadge } from "../components/SeverityBadge";
import { MaterialIcon } from "../components/MaterialIcon";

function buildTimelineData(events: Event[]) {
  const buckets: Record<
    string,
    { safe: number; warning: number; blocked: number }
  > = {};
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
  return Object.entries(buckets).map(([hour, counts]) => ({
    hour,
    ...counts,
  }));
}

function buildTopRules(rules: Rule[]) {
  return [...rules]
    .sort((a, b) => b.hit_count - a.hit_count)
    .slice(0, 5)
    .map((r) => ({ name: r.name, hits: r.hit_count, severity: r.severity }));
}

function severityIconBg(severity: string): string {
  switch (severity) {
    case "blocked":
      return "bg-accent/10 text-accent";
    case "warning":
      return "bg-warning/10 text-warning";
    default:
      return "bg-success/10 text-success";
  }
}

function severityIcon(severity: string): string {
  switch (severity) {
    case "blocked":
      return "gpp_maybe";
    case "warning":
      return "visibility_off";
    default:
      return "check_circle";
  }
}

function severityTextColor(severity: string): string {
  switch (severity) {
    case "blocked":
      return "text-accent";
    case "warning":
      return "text-warning";
    default:
      return "text-success-light";
  }
}

function severityDotColor(severity: string): string {
  switch (severity) {
    case "blocked":
      return "bg-accent";
    case "warning":
      return "bg-warning";
    default:
      return "bg-success";
  }
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
        const [s, e, r] = await Promise.all([
          fetchStatus(),
          fetchEvents(),
          fetchRules(),
        ]);
        setStatus(s);
        setEvents(e);
        setRules(r);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load dashboard data",
        );
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
        <MaterialIcon
          icon="progress_activity"
          className="animate-spin text-gray-500 text-3xl"
        />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-accent/30 bg-accent/10 px-4 py-8 text-center text-sm text-accent">
        {error}
      </div>
    );
  }

  if (!status) return null;

  const hasCriticalViolations = status.violations > 0;

  return (
    <div className="space-y-8">
      {/* Alert Banner */}
      {hasCriticalViolations && (
        <div className="bg-accent/20 border border-accent/30 rounded-xl p-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-full bg-accent/20 flex items-center justify-center text-accent">
              <MaterialIcon icon="warning" className="text-lg" filled />
            </div>
            <div>
              <h4 className="font-bold text-accent tracking-tight">
                CRITICAL VIOLATION DETECTED
              </h4>
              <p className="text-sm text-gray-400">
                {status.violations} violation
                {status.violations !== 1 && "s"} detected today &mdash;{" "}
                {status.blocked_actions} action
                {status.blocked_actions !== 1 && "s"} blocked
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Bento Top Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* Events Today */}
        <div className="bg-gray-900 p-6 rounded-2xl relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:scale-110 transition-transform">
            <MaterialIcon icon="analytics" className="text-4xl" />
          </div>
          <p className="text-[10px] uppercase tracking-[0.2em] text-gray-400 font-bold mb-2">
            Events Today
          </p>
          <div className="flex items-baseline gap-2">
            <h3 className="text-3xl font-bold tracking-tighter text-gray-50">
              {formatNumber(status.events_today)}
            </h3>
          </div>
        </div>

        {/* Violations */}
        <div className="bg-gray-900 p-6 rounded-2xl relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:scale-110 transition-transform">
            <MaterialIcon icon="security_update_warning" className="text-4xl text-accent" />
          </div>
          <p className="text-[10px] uppercase tracking-[0.2em] text-gray-400 font-bold mb-2">
            Violations
          </p>
          <div className="flex items-baseline gap-2">
            <h3 className="text-3xl font-bold tracking-tighter text-accent">
              {formatNumber(status.violations)}
            </h3>
          </div>
        </div>

        {/* Blocked Actions */}
        <div className="bg-gray-900 p-6 rounded-2xl relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:scale-110 transition-transform">
            <MaterialIcon icon="block" className="text-4xl" />
          </div>
          <p className="text-[10px] uppercase tracking-[0.2em] text-gray-400 font-bold mb-2">
            Blocked Actions
          </p>
          <div className="flex items-baseline gap-2">
            <h3 className="text-3xl font-bold tracking-tighter text-gray-50">
              {formatNumber(status.blocked_actions)}
            </h3>
          </div>
        </div>

        {/* Cost Total */}
        <div className="bg-gray-900 p-6 rounded-2xl relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:scale-110 transition-transform">
            <MaterialIcon icon="payments" className="text-4xl" />
          </div>
          <p className="text-[10px] uppercase tracking-[0.2em] text-gray-400 font-bold mb-2">
            Cost Total
          </p>
          <div className="flex items-baseline gap-2">
            <h3 className="text-3xl font-bold tracking-tighter text-gray-400">
              {status.cost_total}
            </h3>
          </div>
        </div>
      </div>

      {/* Middle Visualization & Feed */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-10">
        {/* Timeline Chart */}
        <div className="lg:col-span-2 bg-gray-900 p-8 rounded-3xl flex flex-col">
          <div className="flex justify-between items-center mb-8">
            <div>
              <h4 className="text-lg font-bold tracking-tight text-gray-50">
                Event Timeline
              </h4>
              <p className="text-xs text-gray-400">
                Real-time event frequency (24h Window)
              </p>
            </div>
            <div className="flex gap-4">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-success" />
                <span className="text-[10px] uppercase font-bold text-gray-400">
                  Safe
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-warning" />
                <span className="text-[10px] uppercase font-bold text-gray-400">
                  Warning
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-accent" />
                <span className="text-[10px] uppercase font-bold text-gray-400">
                  Blocked
                </span>
              </div>
            </div>
          </div>
          <div className="flex-1 min-h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={timelineData}>
                <defs>
                  <linearGradient id="gradSafe" x1="0" y1="0" x2="0" y2="1">
                    <stop
                      offset="0%"
                      stopColor={theme.success}
                      stopOpacity={0.4}
                    />
                    <stop
                      offset="100%"
                      stopColor={theme.success}
                      stopOpacity={0.05}
                    />
                  </linearGradient>
                  <linearGradient id="gradWarn" x1="0" y1="0" x2="0" y2="1">
                    <stop
                      offset="0%"
                      stopColor={theme.warning}
                      stopOpacity={0.4}
                    />
                    <stop
                      offset="100%"
                      stopColor={theme.warning}
                      stopOpacity={0.05}
                    />
                  </linearGradient>
                  <linearGradient
                    id="gradBlocked"
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                  >
                    <stop
                      offset="0%"
                      stopColor={theme.accent}
                      stopOpacity={0.4}
                    />
                    <stop
                      offset="100%"
                      stopColor={theme.accent}
                      stopOpacity={0.05}
                    />
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
                  strokeWidth={2}
                />
                <Area
                  type="monotone"
                  dataKey="warning"
                  stackId="1"
                  stroke={theme.warning}
                  fill="url(#gradWarn)"
                  strokeWidth={2}
                />
                <Area
                  type="monotone"
                  dataKey="blocked"
                  stackId="1"
                  stroke={theme.accent}
                  fill="url(#gradBlocked)"
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Live Event Feed */}
        <div className="bg-gray-900 rounded-3xl overflow-hidden flex flex-col h-[420px]">
          <div className="p-6 border-b border-gray-800/10">
            <h4 className="text-sm font-bold tracking-tight text-gray-50">
              Live Event Feed
            </h4>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-2">
            {events.length === 0 ? (
              <p className="py-8 text-center text-sm text-gray-500">
                No events yet
              </p>
            ) : (
              events.slice(0, 20).map((event) => (
                <div
                  key={event.id}
                  className="p-4 bg-gray-950 rounded-xl flex items-start gap-4 hover:bg-gray-800 transition-colors"
                >
                  <div className={cn(
                    "w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0",
                    severityIconBg(event.severity),
                  )}>
                    <MaterialIcon
                      icon={severityIcon(event.severity)}
                      className="text-lg"
                      filled={event.severity === "blocked"}
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between items-center mb-1">
                      <span className={cn(
                        "text-[10px] font-bold uppercase",
                        severityTextColor(event.severity),
                      )}>
                        {event.severity === "blocked" ? "Blocked" : event.severity === "warning" ? "Warning" : "Safe"}
                      </span>
                      <span className="text-[10px] text-gray-500">
                        {formatTime(event.timestamp)}
                      </span>
                    </div>
                    <p className="text-xs font-medium text-gray-100 truncate">
                      {event.action}
                    </p>
                    <p className="text-[10px] text-gray-500">
                      {event.agent_id}
                      {event.rule_name && ` | ${event.rule_name}`}
                    </p>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Bottom Table Section */}
      <div className="bg-gray-900 rounded-3xl overflow-hidden">
        <div className="px-8 py-6 border-b border-gray-800/10 flex items-center justify-between">
          <h4 className="font-bold tracking-tight text-gray-50">
            Top Triggered Rules
          </h4>
          <button className="text-xs font-bold text-accent hover:underline">View All Rules</button>
        </div>
        {topRules.length === 0 ? (
          <p className="py-8 text-center text-sm text-gray-500">
            No rules configured
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="bg-gray-950">
                <tr>
                  <th className="px-6 py-4 text-[10px] uppercase font-bold tracking-widest text-gray-500">
                    Rule Name
                  </th>
                  <th className="px-6 py-4 text-[10px] uppercase font-bold tracking-widest text-gray-500">
                    Severity
                  </th>
                  <th className="px-6 py-4 text-[10px] uppercase font-bold tracking-widest text-gray-500">
                    Hits
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/30">
                {topRules.map((rule) => (
                  <tr
                    key={rule.name}
                    className="hover:bg-gray-850 transition-colors"
                  >
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div
                          className={cn(
                            "w-2 h-2 rounded-full",
                            severityDotColor(rule.severity),
                          )}
                        />
                        <span className="text-sm font-semibold text-gray-100">
                          {rule.name}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <SeverityBadge severity={rule.severity} />
                    </td>
                    <td className="px-6 py-4 font-mono text-sm text-gray-300">
                      {formatNumber(rule.hits)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
