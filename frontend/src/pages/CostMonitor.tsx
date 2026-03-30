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
import { cn, formatNumber } from "../lib/utils";
import { theme } from "../lib/theme";
import { fetchCosts } from "../lib/api";
import type { CostData } from "../lib/api";
import { MaterialIcon } from "../components/MaterialIcon";

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
        <MaterialIcon
          icon="progress_activity"
          className="animate-spin text-gray-500 text-3xl"
        />
      </div>
    );
  }

  if (error || !costs) {
    return (
      <div className="rounded-xl border border-accent/30 bg-accent/10 px-4 py-8 text-center text-sm text-accent">
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
      <div className="bg-gray-900 rounded-xl border border-gray-800/40 p-6">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className={cn(
                "flex h-9 w-9 items-center justify-center rounded-lg",
                isOverBudget
                  ? "bg-accent/15"
                  : isWarning
                    ? "bg-warning/15"
                    : "bg-success/15",
              )}
            >
              <MaterialIcon
                icon="account_balance_wallet"
                className={cn(
                  "text-lg",
                  isOverBudget
                    ? "text-accent"
                    : isWarning
                      ? "text-warning"
                      : "text-success-light",
                )}
                filled
              />
            </div>
            <div>
              <p className="text-sm font-semibold text-gray-100">Daily Budget</p>
              <p className="text-xs text-gray-500">
                {costs.spent} of {costs.budget}
              </p>
            </div>
          </div>
          <span
            className={cn(
              "text-3xl font-extrabold tracking-tighter",
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
      <div className="bg-gray-900 rounded-xl border border-gray-800/40 p-8 flex flex-col">
        <div className="flex justify-between items-center mb-8">
          <div>
            <h4 className="text-lg font-bold tracking-tight text-gray-50">
              30-Day Cost Trend
            </h4>
            <p className="text-xs text-gray-400 uppercase tracking-widest mt-1">
              Daily Spending Overview
            </p>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-accent" />
              <span className="text-[10px] uppercase font-bold text-gray-400">
                Cost
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-5 border-t-2 border-dashed border-warning" />
              <span className="text-[10px] uppercase font-bold text-gray-400">
                Budget
              </span>
            </div>
          </div>
        </div>
        <div className="h-[300px]">
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
      <div className="bg-gray-900 rounded-xl border border-gray-800/40 overflow-hidden">
        <div className="p-6 border-b border-gray-800/40 flex items-center justify-between">
          <h4 className="text-lg font-bold tracking-tight text-gray-50">
            Cost Breakdown by Agent
          </h4>
        </div>
        {costs.agents.length === 0 ? (
          <p className="py-8 text-center text-sm text-gray-500">No agent cost data</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="bg-gray-950">
                <tr>
                  <th className="px-6 py-4 text-[10px] uppercase font-bold tracking-widest text-gray-500">
                    Agent
                  </th>
                  <th className="px-6 py-4 text-[10px] uppercase font-bold tracking-widest text-gray-500 text-right">
                    Requests
                  </th>
                  <th className="px-6 py-4 text-[10px] uppercase font-bold tracking-widest text-gray-500 text-right">
                    Tokens
                  </th>
                  <th className="px-6 py-4 text-[10px] uppercase font-bold tracking-widest text-gray-500 text-right">
                    Cost
                  </th>
                  <th className="px-6 py-4 text-[10px] uppercase font-bold tracking-widest text-gray-500 text-right">
                    %
                  </th>
                  <th className="px-6 py-4 text-[10px] uppercase font-bold tracking-widest text-gray-500 text-right">
                    7d Trend
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/30">
                {costs.agents.map((agent) => {
                  const isAnomaly = costs.anomalies.includes(agent.agent_id);
                  return (
                    <tr
                      key={agent.agent_id}
                      className={cn(
                        "hover:bg-gray-850 transition-colors",
                        isAnomaly && "bg-accent/5",
                      )}
                    >
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          {isAnomaly && (
                            <MaterialIcon
                              icon="warning"
                              className="text-sm text-accent"
                              filled
                            />
                          )}
                          <span className="font-semibold text-sm text-gray-100">
                            {agent.agent_name}
                          </span>
                          {isAnomaly && (
                            <span className="rounded-md bg-accent/10 px-1.5 py-0.5 text-[10px] font-medium text-accent">
                              Anomaly
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-4 text-right font-mono text-sm text-gray-300">
                        {formatNumber(agent.requests)}
                      </td>
                      <td className="px-6 py-4 text-right font-mono text-sm text-gray-300">
                        {(agent.tokens / 1000).toFixed(0)}k
                      </td>
                      <td className="px-6 py-4 text-right font-mono text-sm font-semibold text-gray-100">
                        {agent.cost}
                      </td>
                      <td className="px-6 py-4 text-right text-sm text-gray-400">
                        {agent.percentage.toFixed(1)}%
                      </td>
                      <td className="px-6 py-4 text-right">
                        <Sparkline data={agent.daily_costs} anomaly={isAnomaly} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
