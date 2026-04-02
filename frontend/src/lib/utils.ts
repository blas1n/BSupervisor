export function cn(...classes: (string | false | undefined | null)[]): string {
  return classes.filter(Boolean).join(" ");
}

export function formatNumber(n: number): string {
  return n.toLocaleString("en-US");
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function severityColor(severity: string): string {
  switch (severity) {
    case "critical":
      return "text-accent bg-accent/10";
    case "high":
      return "text-warning bg-warning/10";
    case "medium":
      return "text-warning-light bg-warning-light/10";
    case "low":
      return "text-success-light bg-success-light/10";
    default:
      return "text-gray-400 bg-gray-400/10";
  }
}