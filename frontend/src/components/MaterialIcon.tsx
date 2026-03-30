import { cn } from "../lib/utils";

export function MaterialIcon({
  icon,
  className,
  filled,
}: {
  icon: string;
  className?: string;
  filled?: boolean;
}) {
  return (
    <span
      className={cn("material-symbols-outlined", className)}
      style={filled ? { fontVariationSettings: "'FILL' 1" } : undefined}
    >
      {icon}
    </span>
  );
}
