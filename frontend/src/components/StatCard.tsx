import type { LucideIcon } from "lucide-react";
import { cn } from "../lib/utils";

interface StatCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  accent?: boolean;
  trend?: { value: string; positive: boolean };
}

export function StatCard({
  label,
  value,
  icon: Icon,
  accent,
  trend,
}: StatCardProps) {
  return (
    <div className="card-hover rounded-xl border border-gray-800 bg-gray-900 p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium tracking-wide text-gray-500 uppercase">
            {label}
          </p>
          <p
            className={cn(
              "mt-2 text-2xl font-bold tabular-nums",
              accent ? "text-accent" : "text-gray-50",
            )}
          >
            {value}
          </p>
          {trend && (
            <p
              className={cn(
                "mt-1 text-xs font-medium",
                trend.positive ? "text-success-light" : "text-accent",
              )}
            >
              {trend.value}
            </p>
          )}
        </div>
        <div
          className={cn(
            "flex h-10 w-10 items-center justify-center rounded-lg",
            accent
              ? "bg-gradient-to-br from-accent/20 to-accent/10"
              : "bg-gray-800/80",
          )}
        >
          <Icon
            className={cn(
              "h-5 w-5",
              accent ? "text-accent" : "text-gray-400",
            )}
          />
        </div>
      </div>
    </div>
  );
}
