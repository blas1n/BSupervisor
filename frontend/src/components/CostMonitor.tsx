"use client";

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
import { useT } from "@bsvibe/i18n";
import { ResponsiveTable } from "@bsvibe/ui";
import type { ResponsiveTableColumn } from "@bsvibe/ui";
import { cn, formatNumber } from "../lib/utils";
import { theme } from "../lib/theme";
import { fetchCosts, fetchAnomalies } from "../lib/api";
import type { CostData, AnomalyEntry } from "../lib/api";

type AgentCost = CostData["agents"][number];
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
  const t = useT("supervisor.costs");
  const [costs, setCosts] = useState<CostData | null>(null);
  const [anomalyDetails, setAnomalyDetails] = useState<AnomalyEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [data, anomalies] = await Promise.all([fetchCosts(), fetchAnomalies()]);
        setCosts(data);
        setAnomalyDetails(anomalies);
      } catch (err) {
        // Empty sentinel = "failed without a message"; the i18n fallback
        // is resolved at render so `t` stays out of the effect deps.
        setError(err instanceof Error ? err.message : "");
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

  if (error !== null || !costs) {
    return (
      <div className="rounded-xl border border-accent/30 bg-accent/10 px-4 py-8 text-center text-sm text-accent">
        {error ? error : error === "" ? t("loadError") : t("emptyData")}
      </div>
    );
  }

  const isOverBudget = costs.budget_percentage > 100;
  const isWarning = costs.budget_percentage > 80;
  const budgetNum = parseFloat(costs.budget.replace("$", ""));

  const isAnomalyAgent = (agent: AgentCost) =>
    costs.anomalies.includes(agent.agent_id);
  const anomalyInfoFor = (agent: AgentCost) =>
    anomalyDetails.find((a) => a.agent_id === agent.agent_id);

  const agentColumns: ResponsiveTableColumn<AgentCost>[] = [
    {
      key: "agent",
      header: t("colAgent"),
      cellClassName: "px-6 py-4",
      cell: (agent) => {
        const isAnomaly = isAnomalyAgent(agent);
        const anomalyInfo = anomalyInfoFor(agent);
        return (
          <>
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
                <span
                  className="rounded-md bg-accent/10 px-1.5 py-0.5 text-[10px] font-medium text-accent"
                  data-testid="anomaly-badge"
                >
                  {t("anomalyBadge")}
                </span>
              )}
            </div>
            {anomalyInfo && (
              <p
                className="text-[10px] text-accent mt-1"
                data-testid="anomaly-detail"
              >
                {t("anomalyDetail", {
                  multiplier: anomalyInfo.multiplier,
                  baseline: anomalyInfo.baseline_mean,
                })}
              </p>
            )}
          </>
        );
      },
    },
    {
      key: "requests",
      header: t("colRequests"),
      cellClassName: "px-6 py-4 text-right font-mono text-sm text-gray-300",
      cell: (agent) => formatNumber(agent.requests),
    },
    {
      key: "tokens",
      header: t("colTokens"),
      cellClassName: "px-6 py-4 text-right font-mono text-sm text-gray-300",
      cell: (agent) => `${(agent.tokens / 1000).toFixed(0)}k`,
    },
    {
      key: "cost",
      header: t("colCost"),
      cellClassName:
        "px-6 py-4 text-right font-mono text-sm font-semibold text-gray-100",
      cell: (agent) => agent.cost,
    },
    {
      key: "percent",
      header: t("colPercent"),
      cellClassName: "px-6 py-4 text-right text-sm text-gray-400",
      cell: (agent) => `${agent.percentage.toFixed(1)}%`,
    },
    {
      key: "trend",
      header: t("colTrend"),
      cellClassName: "px-6 py-4 text-right",
      cell: (agent) => (
        <Sparkline data={agent.daily_costs} anomaly={isAnomalyAgent(agent)} />
      ),
    },
  ];

  const renderAgentMobileCard = (agent: AgentCost) => {
    const isAnomaly = isAnomalyAgent(agent);
    const anomalyInfo = anomalyInfoFor(agent);
    return (
      <article
        data-testid="bsvibe-table-card"
        className={cn(
          "rounded-md border border-gray-800 bg-gray-900 p-4 flex flex-col gap-2",
          isAnomaly && "border-accent/30 bg-accent/5",
        )}
      >
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
            <span
              className="rounded-md bg-accent/10 px-1.5 py-0.5 text-[10px] font-medium text-accent"
              data-testid="anomaly-badge"
            >
              {t("anomalyBadge")}
            </span>
          )}
        </div>
        {anomalyInfo && (
          <p className="text-[10px] text-accent" data-testid="anomaly-detail">
            {t("anomalyDetail", {
              multiplier: anomalyInfo.multiplier,
              baseline: anomalyInfo.baseline_mean,
            })}
          </p>
        )}
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
          <dt className="uppercase tracking-wide text-gray-400">
            {t("colRequests")}
          </dt>
          <dd className="text-right font-mono text-gray-300">
            {formatNumber(agent.requests)}
          </dd>
          <dt className="uppercase tracking-wide text-gray-400">
            {t("colTokens")}
          </dt>
          <dd className="text-right font-mono text-gray-300">
            {(agent.tokens / 1000).toFixed(0)}k
          </dd>
          <dt className="uppercase tracking-wide text-gray-400">
            {t("colCost")}
          </dt>
          <dd className="text-right font-mono font-semibold text-gray-100">
            {agent.cost}
          </dd>
          <dt className="uppercase tracking-wide text-gray-400">
            {t("colPercent")}
          </dt>
          <dd className="text-right text-gray-400">
            {agent.percentage.toFixed(1)}%
          </dd>
        </dl>
        <div className="flex items-center justify-between pt-1">
          <span className="text-xs uppercase tracking-wide text-gray-400">
            {t("colTrend")}
          </span>
          <Sparkline data={agent.daily_costs} anomaly={isAnomaly} />
        </div>
      </article>
    );
  };

  return (
    <div className="space-y-6">
      {/* Budget progress */}
      <div className="bg-gray-900 rounded-lg p-6 relative overflow-hidden border border-gray-800/10">
        <div className="flex justify-between items-end mb-4">
          <div>
            <span className="text-[10px] uppercase tracking-widest text-gray-500 block mb-1">{t("consumptionLabel")}</span>
            <div className="text-3xl font-extrabold tracking-tighter text-gray-50">
              {costs.spent} <span className="text-sm font-normal text-gray-500">{t("budgetSuffix", { budget: costs.budget })}</span>
            </div>
          </div>
          <div className="text-right">
            {isOverBudget ? (
              <span className="text-xs font-bold text-accent flex items-center gap-1">
                <MaterialIcon icon="trending_up" className="text-sm" />
                {t("overBudget", { percent: Math.round(costs.budget_percentage - 100) })}
              </span>
            ) : isWarning ? (
              <span className="text-xs font-bold text-warning flex items-center gap-1">
                <MaterialIcon icon="trending_up" className="text-sm" />
                {t("approachingLimit")}
              </span>
            ) : (
              <span className="text-xs font-bold text-success-light flex items-center gap-1">
                {t("onTrack")}
              </span>
            )}
          </div>
        </div>
        <div className="h-1.5 w-full bg-gray-800 rounded-full overflow-hidden">
          <div
            className={cn(
              "h-full transition-all",
              isOverBudget
                ? "bg-accent shadow-[0_0_15px_rgba(244,63,94,0.4)]"
                : isWarning
                  ? "bg-warning"
                  : "bg-success",
            )}
            style={{ width: `${Math.min(costs.budget_percentage, 100)}%` }}
          />
        </div>
        <div className="mt-2 flex justify-between text-[10px] text-gray-500 font-medium">
          <span>0%</span>
          <span>50%</span>
          <span>100%</span>
        </div>
      </div>

      {/* 30-day trend */}
      <div>
        <div className="flex items-center gap-2 mb-6">
          <div className="w-0.5 h-4 bg-accent" />
          <h2 className="text-sm font-bold tracking-tight uppercase text-gray-50">{t("trendTitle")}</h2>
        </div>
      <div className="bg-gray-900 rounded-lg p-8 flex flex-col">
        <div className="flex justify-between items-center mb-8">
          <div></div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-accent" />
              <span className="text-[10px] uppercase font-bold text-gray-400">
                {t("legendCost")}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-5 border-t-2 border-dashed border-warning" />
              <span className="text-[10px] uppercase font-bold text-gray-400">
                {t("legendBudget")}
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
                  value: t("legendBudget"),
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
                formatter={(value) => [`$${Number(value).toFixed(2)}`, t("legendCost")]}
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
      </div>

      {/* Agent cost breakdown */}
      <div>
        <div className="flex items-center gap-2 mb-6">
          <div className="w-0.5 h-4 bg-accent" />
          <h2 className="text-sm font-bold tracking-tight uppercase text-gray-50">{t("breakdownTitle")}</h2>
        </div>
      <div className="bg-gray-900 rounded-lg overflow-hidden p-4">
        <ResponsiveTable
          columns={agentColumns}
          rows={costs.agents}
          rowKey={(agent) => agent.agent_id}
          renderMobileCard={renderAgentMobileCard}
          emptyMessage={t("breakdownEmpty")}
        />
      </div>
      </div>
    </div>
  );
}
