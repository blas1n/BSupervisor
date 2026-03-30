import { useState, useEffect } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { DollarSign, TrendingUp, AlertTriangle, Loader2 } from "lucide-react";
import { cn, formatNumber } from "../lib/utils";
import { theme } from "../lib/theme";
import { fetchCosts } from "../lib/api";
import type { CostData } from "../lib/api";

function Sparkline({ data, anomaly }: { data: number[]; anomaly?: boolean }) {
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const w = 80;
  const h = 24;

  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * w;
      const y = h - ((v - min) / range) * h;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg width={w} height={h} className="inline-block">
      <polyline
        points={points}
        fill="none"
        stroke={anomaly ? theme.accent : theme.gray400}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function CostMonitor() {
  const [costs, setCosts] = useState<CostData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const data = await fetchCosts();
        setCosts(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load cost data");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-gray-500" />
      </div>
    );
  }

  if (error || !costs) {
    return (
      <div className="rounded-lg border border-accent/30 bg-accent/10 px-4 py-8 text-center text-sm text-accent">
        {error ?? "No cost data available"}
      </div>
    );
  }

  const isOverBudget = costs.budget_percentage > 100;
  const isWarning = costs.budget_percentage > 80;
  const budgetNum = parseFloat(costs.budget.replace("$", ""));

  return (
    <div className="space-y-6">
      {/* Budget progress */}
      <div className="rounded-lg border border-gray-800 bg-gray-900 p-5">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-md",
                isOverBudget
                  ? "bg-accent/15"
                  : isWarning
                    ? "bg-warning/15"
                    : "bg-success/15",
              )}
            >
              <DollarSign
                className={cn(
                  "h-4 w-4",
                  isOverBudget
                    ? "text-accent"
                    : isWarning
                      ? "text-warning"
                      : "text-success-light",
                )}
              />
            </div>
            <div>
              <p className="text-sm font-medium text-gray-300">Daily Budget</p>
              <p className="text-xs text-gray-500">
                {costs.spent} of {costs.budget}
              </p>
            </div>
          </div>
          <span
            className={cn(
              "text-2xl font-bold",
              isOverBudget
                ? "text-accent"
                : isWarning
                  ? "text-warning"
                  : "text-success-light",
            )}
          >
            {costs.budget_percentage.toFixed(1)}%
          </span>
        </div>
        <div className="h-2.5 overflow-hidden rounded-full bg-gray-800">
          <div
            className={cn(
              "h-full rounded-full transition-all",
              isOverBudget
                ? "bg-accent"
                : isWarning
                  ? "bg-warning"
                  : "bg-success",
            )}
            style={{ width: `${Math.min(costs.budget_percentage, 100)}%` }}
          />
        </div>
        {isWarning && !isOverBudget && (
          <p className="mt-2 text-xs text-warning/80">
            Approaching budget limit
          </p>
        )}
      </div>

      {/* 30-day trend */}
      <div className="rounded-lg border border-gray-800 bg-gray-900 p-5">
        <div className="mb-4 flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-gray-400" />
          <h2 className="text-sm font-semibold text-gray-300">
            30-Day Cost Trend
          </h2>
        </div>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={costs.trend}>
              <defs>
                <linearGradient id="costGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={theme.accent} stopOpacity={0.15} />
                  <stop offset="100%" stopColor={theme.accent} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: theme.gray400 }}
                tickFormatter={(d: string) => d.slice(5)}
                interval={4}
              />
              <YAxis
                tick={{ fontSize: 11, fill: theme.gray400 }}
                tickFormatter={(v: number) => `$${v}`}
              />
              <ReferenceLine
                y={budgetNum}
                stroke={theme.warning}
                strokeDasharray="4 4"
                strokeOpacity={0.5}
                label={{
                  value: "Budget",
                  fill: theme.warning,
                  fontSize: 10,
                  position: "right",
                }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: theme.gray800,
                  border: `1px solid ${theme.gray700}`,
                  borderRadius: 8,
                  fontSize: 12,
                }}
                formatter={(value) => [`$${Number(value).toFixed(2)}`, "Cost"]}
                labelStyle={{ color: theme.gray300 }}
              />
              <Line
                type="monotone"
                dataKey="cost"
                stroke={theme.accent}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, stroke: theme.accent, fill: theme.gray800 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Agent cost breakdown */}
      <div className="rounded-lg border border-gray-800 bg-gray-900 p-5">
        <h2 className="mb-4 text-sm font-semibold text-gray-300">
          Cost Breakdown by Agent
        </h2>
        {costs.agents.length === 0 ? (
          <p className="py-4 text-center text-sm text-gray-500">No agent cost data</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-left text-xs font-medium text-gray-500">
                <th className="pb-3 pr-4">Agent</th>
                <th className="pb-3 pr-4 text-right">Requests</th>
                <th className="pb-3 pr-4 text-right">Tokens</th>
                <th className="pb-3 pr-4 text-right">Cost</th>
                <th className="pb-3 pr-4 text-right">%</th>
                <th className="pb-3 text-right">7d Trend</th>
              </tr>
            </thead>
            <tbody>
              {costs.agents.map((agent) => {
                const isAnomaly = costs.anomalies.includes(agent.agent_id);
                return (
                  <tr
                    key={agent.agent_id}
                    className={cn(
                      "border-b border-gray-800/50 last:border-0",
                      isAnomaly && "bg-accent/5",
                    )}
                  >
                    <td className="py-3.5 pr-4">
                      <div className="flex items-center gap-2">
                        {isAnomaly && (
                          <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0 text-accent" />
                        )}
                        <span className="font-medium text-gray-100">
                          {agent.agent_name}
                        </span>
                        {isAnomaly && (
                          <span className="rounded-md bg-accent/10 px-1.5 py-0.5 text-[10px] font-medium text-accent">
                            Anomaly
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-3.5 pr-4 text-right font-mono text-gray-300">
                      {formatNumber(agent.requests)}
                    </td>
                    <td className="py-3.5 pr-4 text-right font-mono text-gray-300">
                      {(agent.tokens / 1000).toFixed(0)}k
                    </td>
                    <td className="py-3.5 pr-4 text-right font-mono font-medium text-gray-100">
                      {agent.cost}
                    </td>
                    <td className="py-3.5 pr-4 text-right text-gray-400">
                      {agent.percentage.toFixed(1)}%
                    </td>
                    <td className="py-3.5 text-right">
                      <Sparkline data={agent.daily_costs} anomaly={isAnomaly} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
