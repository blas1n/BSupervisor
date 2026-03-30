import { useState, useMemo, useEffect } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { fetchDailyReport } from "../lib/api";
import type { DailyReportData } from "../lib/api";
import { MaterialIcon } from "../components/MaterialIcon";

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function parseMarkdown(md: string): string {
  // Escape HTML entities first to prevent XSS
  let html = escapeHtml(md);

  // Headers
  html = html.replace(
    /^### (.+)$/gm,
    '<h3 class="mt-5 mb-2 text-base font-semibold text-gray-100">$1</h3>',
  );
  html = html.replace(
    /^## (.+)$/gm,
    '<h2 class="mt-6 mb-3 text-lg font-semibold text-gray-50">$1</h2>',
  );
  html = html.replace(
    /^# (.+)$/gm,
    '<h1 class="mb-4 text-xl font-bold text-gray-50">$1</h1>',
  );

  // Bold
  html = html.replace(
    /\*\*(.+?)\*\*/g,
    '<strong class="font-semibold text-gray-100">$1</strong>',
  );

  // Inline code
  html = html.replace(
    /`([^`]+)`/g,
    '<code class="rounded-sm bg-gray-800 px-1.5 py-0.5 font-mono text-xs text-accent-light">$1</code>',
  );

  // Tables
  html = html.replace(
    /^\|(.+)\|\s*\n\|[-| :]+\|\s*\n((?:\|.+\|\s*\n?)*)/gm,
    (_match, header: string, body: string) => {
      const ths = header
        .split("|")
        .map((c: string) => c.trim())
        .filter(Boolean)
        .map(
          (c: string) =>
            `<th class="px-6 py-4 text-left text-[10px] uppercase font-bold tracking-widest text-gray-500">${c}</th>`,
        )
        .join("");
      const rows = body
        .trim()
        .split("\n")
        .map((row: string) => {
          const tds = row
            .split("|")
            .map((c: string) => c.trim())
            .filter(Boolean)
            .map(
              (c: string) =>
                `<td class="px-6 py-4 text-sm text-gray-300">${c}</td>`,
            )
            .join("");
          return `<tr class="border-b border-gray-800/30">${tds}</tr>`;
        })
        .join("");
      return `<div class="my-4 overflow-hidden rounded-xl border border-gray-800/40"><table class="w-full"><thead class="bg-gray-950"><tr>${ths}</tr></thead><tbody>${rows}</tbody></table></div>`;
    },
  );

  // Unordered lists
  html = html.replace(
    /^- (.+)$/gm,
    '<li class="ml-4 text-sm text-gray-300 list-disc">$1</li>',
  );
  html = html.replace(
    /((?:<li[^>]*>.*<\/li>\s*)+)/g,
    '<ul class="my-2 space-y-1">$1</ul>',
  );

  // Paragraphs
  html = html.replace(
    /^(?!<[a-z])((?!^\s*$).+)$/gm,
    '<p class="my-2 text-sm leading-relaxed text-gray-300">$1</p>',
  );

  return html;
}

export function DailyReport() {
  const today = new Date().toISOString().slice(0, 10);
  const [date, setDate] = useState(today);
  const [report, setReport] = useState<DailyReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchDailyReport(date);
        if (!cancelled) setReport(data);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load report");
          setReport(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [date]);

  const renderedHtml = useMemo(
    () => (report ? parseMarkdown(report.markdown) : ""),
    [report],
  );

  function changeDate(delta: number) {
    const d = new Date(date);
    d.setDate(d.getDate() + delta);
    setDate(d.toISOString().slice(0, 10));
  }

  const displayDate = new Date(date + "T12:00:00").toLocaleDateString(
    "en-US",
    {
      weekday: "long",
      year: "numeric",
      month: "long",
      day: "numeric",
    },
  );

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      {/* Date navigation */}
      <div className="flex items-center justify-between rounded-xl border border-gray-800/40 bg-gray-900 px-6 py-4">
        <div className="flex items-center gap-3">
          <MaterialIcon icon="calendar_today" className="text-lg text-gray-500" />
          <button
            onClick={() => changeDate(-1)}
            className="rounded-lg border border-gray-800/40 p-1.5 text-gray-400 transition-colors hover:bg-gray-800 hover:text-gray-200"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
          <span className="min-w-56 text-center text-sm font-semibold text-gray-100">
            {displayDate}
          </span>
          <button
            onClick={() => changeDate(1)}
            disabled={date >= today}
            className="rounded-lg border border-gray-800/40 p-1.5 text-gray-400 transition-colors hover:bg-gray-800 hover:text-gray-200 disabled:opacity-30"
          >
            <ChevronRight className="h-5 w-5" />
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button className="flex items-center gap-2 rounded-xl border border-gray-800/40 px-3 py-2 text-xs font-medium text-gray-400 transition-colors hover:bg-gray-800 hover:text-gray-200">
            <MaterialIcon icon="download" className="text-sm" />
            PDF
          </button>
          <button className="flex items-center gap-2 rounded-xl border border-gray-800/40 px-3 py-2 text-xs font-medium text-gray-400 transition-colors hover:bg-gray-800 hover:text-gray-200">
            <MaterialIcon icon="description" className="text-sm" />
            Markdown
          </button>
        </div>
      </div>

      {/* Report card */}
      <div className="rounded-xl border border-gray-800/40 bg-gray-900 p-8">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <MaterialIcon
              icon="progress_activity"
              className="animate-spin text-gray-500 text-3xl"
            />
          </div>
        ) : error ? (
          <p className="py-12 text-center text-sm text-gray-500">
            No report available for this date
          </p>
        ) : report ? (
          <div
            className="prose-dark"
            dangerouslySetInnerHTML={{ __html: renderedHtml }}
          />
        ) : (
          <p className="py-12 text-center text-sm text-gray-500">
            No report available for this date
          </p>
        )}
      </div>
    </div>
  );
}
