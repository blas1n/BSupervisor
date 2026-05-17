"use client";

import { useState, useMemo, useEffect } from "react";
import { useT } from "@bsvibe/i18n";
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
  const t = useT("supervisor.reports");
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
          // The error message itself is not surfaced (the card shows the
          // generic empty-state copy); store it only to flip the branch.
          setError(err instanceof Error ? err.message : "");
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

  function downloadMarkdown() {
    if (!report) return;
    const blob = new Blob([report.markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `bsupervisor-report-${date}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function downloadPdf() {
    if (!report) return;
    const doc = window.open("", "_blank");
    if (!doc) return;
    doc.document.write(`<!doctype html>
<html><head><meta charset="utf-8"><title>BSupervisor ${t("heading")} — ${date}</title>
<style>
  @page { margin: 18mm 16mm; }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Inter", system-ui, sans-serif;
    max-width: 760px; margin: 0 auto; padding: 0 1rem;
    color: #0f172a; background: #fff; line-height: 1.55;
  }
  .brand-bar {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 0 10px; border-bottom: 1px solid #e5e7eb; margin-bottom: 28px;
  }
  .brand {
    display: flex; align-items: baseline; gap: 10px;
  }
  .brand-name {
    font-size: 14px; font-weight: 900; letter-spacing: -0.02em; color: #f43f5e;
  }
  .brand-tag {
    font-size: 9px; font-weight: 700; letter-spacing: 0.22em; color: #64748b; text-transform: uppercase;
  }
  .report-id { font-size: 9px; color: #94a3b8; letter-spacing: 0.18em; text-transform: uppercase; }
  .title-block {
    position: relative; padding-left: 14px; margin-bottom: 28px;
  }
  .title-block::before {
    content: ""; position: absolute; left: 0; top: 4px; bottom: 4px; width: 4px;
    background: linear-gradient(180deg, #fb7185 0%, #f43f5e 100%); border-radius: 2px;
  }
  .title-kicker {
    font-size: 10px; font-weight: 800; letter-spacing: 0.28em; color: #f43f5e; text-transform: uppercase;
    margin-bottom: 4px;
  }
  .title-main {
    font-size: 26px; font-weight: 900; letter-spacing: -0.03em; color: #0f172a; margin: 0;
  }
  h1 {
    font-size: 20px; font-weight: 900; letter-spacing: -0.02em; color: #0f172a;
    margin: 32px 0 12px; padding-bottom: 6px; border-bottom: 1px solid #f1f5f9;
  }
  h2 {
    font-size: 15px; font-weight: 800; letter-spacing: -0.01em; color: #f43f5e;
    margin: 24px 0 10px; text-transform: uppercase; letter-spacing: 0.08em;
  }
  h3 {
    font-size: 13px; font-weight: 700; color: #334155; margin: 18px 0 8px;
  }
  p { margin: 8px 0; font-size: 13px; }
  ul, ol { padding-left: 20px; font-size: 13px; }
  li { margin: 4px 0; }
  strong { color: #0f172a; font-weight: 700; }
  code {
    background: #f1f5f9; padding: 2px 5px; border-radius: 3px;
    font-family: "JetBrains Mono", ui-monospace, monospace; font-size: 11.5px; color: #be123c;
  }
  table {
    border-collapse: collapse; width: 100%; margin: 14px 0;
    font-size: 12px; border-left: 3px solid #f43f5e;
  }
  th {
    background: #fafafa; text-align: left; padding: 8px 10px;
    font-size: 9px; font-weight: 800; letter-spacing: 0.16em; text-transform: uppercase; color: #64748b;
    border-bottom: 1px solid #e5e7eb;
  }
  td { padding: 8px 10px; border-bottom: 1px solid #f1f5f9; color: #334155; }
  tr:last-child td { border-bottom: none; }
  .footer {
    margin-top: 48px; padding-top: 12px; border-top: 1px solid #e5e7eb;
    font-size: 9px; letter-spacing: 0.2em; text-transform: uppercase;
    color: #94a3b8; display: flex; justify-content: space-between;
  }
  @media print { body { max-width: none; } }
</style></head>
<body>
  <div class="brand-bar">
    <div class="brand">
      <span class="brand-name">BSupervisor</span>
      <span class="brand-tag">AI Sentinel</span>
    </div>
    <span class="report-id">OBS-${date}</span>
  </div>
  <div class="title-block">
    <div class="title-kicker">${t("pdfKicker")}</div>
    <h1 class="title-main">${displayDate}</h1>
  </div>
  ${renderedHtml}
  <div class="footer">
    <span>${t("pdfGeneratedBy")}</span>
    <span>${displayDate}</span>
  </div>
</body></html>`);
    doc.document.close();
    doc.focus();
    doc.print();
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
    <div className="mx-auto max-w-5xl space-y-8 flex flex-col min-h-full">
      {/* Date navigation & toolbar — title stacks above export buttons on
          mobile so the PDF/MD pair doesn't get clipped at the right edge. */}
      <div className="flex flex-col gap-4 sm:flex-row sm:justify-between sm:items-end">
        <div className="min-w-0">
          <h1 className="text-4xl font-extrabold tracking-tighter mb-2 text-gray-50">
            {t("heading")}
          </h1>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] tracking-widest uppercase text-gray-600 font-bold">
            <span>{t("statusLabel")} <span className="text-success-light">{t("statusOperational")}</span></span>
            <span className="hidden sm:inline">&bull;</span>
            <span>{t("idLabel")} OBS-{date}</span>
          </div>
        </div>
        <div className="flex items-center gap-2 self-start sm:self-auto sm:gap-4">
          <button
            onClick={downloadPdf}
            disabled={!report}
            className="flex items-center gap-2 text-[10px] tracking-widest uppercase font-bold text-gray-100 py-2 px-4 bg-gray-800 hover:bg-gray-700 transition-colors disabled:opacity-40"
          >
            <MaterialIcon icon="picture_as_pdf" className="text-sm" /> {t("exportPdf")}
          </button>
          <button
            onClick={downloadMarkdown}
            disabled={!report}
            className="flex items-center gap-2 text-[10px] tracking-widest uppercase font-bold text-gray-100 py-2 px-4 bg-gray-800 hover:bg-gray-700 transition-colors disabled:opacity-40"
          >
            <MaterialIcon icon="markdown" className="text-sm" /> {t("exportMarkdown")}
          </button>
        </div>
      </div>

      {/* Date picker */}
      <div className="flex items-center justify-center gap-6 text-xs uppercase tracking-widest font-semibold">
        <button
          onClick={() => changeDate(-1)}
          data-testid="date-prev"
          aria-label={t("prevDay")}
          className="inline-flex min-h-10 min-w-10 items-center justify-center rounded-lg text-gray-400 hover:bg-gray-900 hover:text-accent transition-colors"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>
        <span className="text-accent flex items-center gap-2">
          <MaterialIcon icon="event" className="text-sm" />
          {displayDate}
        </span>
        <button
          onClick={() => changeDate(1)}
          disabled={date >= today}
          data-testid="date-next"
          aria-label={t("nextDay")}
          className="inline-flex min-h-10 min-w-10 items-center justify-center rounded-lg text-gray-400 hover:bg-gray-900 hover:text-accent transition-colors disabled:opacity-30"
        >
          <ChevronRight className="h-5 w-5" />
        </button>
      </div>

      {/* Report card — flex-grows to fill remaining viewport so the desktop
          layout doesn't leave a large empty band below sparse reports. */}
      <section className="bg-gray-900 p-12 shadow-2xl relative overflow-hidden flex-1">
        {/* Accent bar */}
        <div className="absolute top-0 left-0 w-1 h-full bg-accent" />

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <MaterialIcon
              icon="progress_activity"
              className="animate-spin text-gray-500 text-3xl"
            />
          </div>
        ) : error ? (
          <p className="py-12 text-center text-sm text-gray-500">
            {t("empty")}
          </p>
        ) : report ? (
          <div
            className="prose-dark styled-markdown"
            dangerouslySetInnerHTML={{ __html: renderedHtml }}
          />
        ) : (
          <p className="py-12 text-center text-sm text-gray-500">
            {t("empty")}
          </p>
        )}
      </section>
    </div>
  );
}
