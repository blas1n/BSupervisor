import { useState } from "react";
import {
  Search,
  Plus,
  Lock,
  X,
  Pencil,
  Trash2,
  Filter,
} from "lucide-react";
import { SeverityBadge } from "../components/SeverityBadge";
import { cn, formatNumber } from "../lib/utils";
import { mockRules } from "../lib/mock-data";
import type { Rule } from "../lib/api";

const ruleTypes = ["action", "pattern", "rate", "cost"];
const severities = ["critical", "high", "medium", "low"];
const actionTypes = ["block", "warn", "log"];

interface RuleFormData {
  name: string;
  type: string;
  pattern: string;
  severity: string;
  action: string;
  description: string;
}

const emptyForm: RuleFormData = {
  name: "",
  type: "pattern",
  pattern: "",
  severity: "medium",
  action: "warn",
  description: "",
};

export function RulesManager() {
  const [rules, setRules] = useState<Rule[]>(mockRules);
  const [search, setSearch] = useState("");
  const [filterType, setFilterType] = useState<string>("all");
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<RuleFormData>(emptyForm);

  const filtered = rules.filter((r) => {
    const matchesSearch =
      r.name.toLowerCase().includes(search.toLowerCase()) ||
      r.pattern.toLowerCase().includes(search.toLowerCase());
    const matchesType = filterType === "all" || r.type === filterType;
    return matchesSearch && matchesType;
  });

  function openCreate() {
    setEditingId(null);
    setForm(emptyForm);
    setModalOpen(true);
  }

  function openEdit(rule: Rule) {
    setEditingId(rule.id);
    setForm({
      name: rule.name,
      type: rule.type,
      pattern: rule.pattern,
      severity: rule.severity,
      action: rule.action,
      description: rule.description ?? "",
    });
    setModalOpen(true);
  }

  function handleSave() {
    if (editingId) {
      setRules((prev) =>
        prev.map((r) => (r.id === editingId ? { ...r, ...form } : r)),
      );
    } else {
      const newRule: Rule = {
        id: `rule-${Date.now()}`,
        ...form,
        enabled: true,
        built_in: false,
        hit_count: 0,
      };
      setRules((prev) => [...prev, newRule]);
    }
    setModalOpen(false);
  }

  function handleDelete(id: string) {
    setRules((prev) => prev.filter((r) => r.id !== id));
  }

  function toggleEnabled(id: string) {
    setRules((prev) =>
      prev.map((r) => (r.id === id ? { ...r, enabled: !r.enabled } : r)),
    );
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            placeholder="Search rules by name or pattern..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-gray-700 bg-gray-900 py-2.5 pl-9 pr-4 text-sm text-gray-100 placeholder-gray-500 outline-none transition-colors focus:border-accent/50 focus:ring-1 focus:ring-accent/30"
          />
        </div>
        <div className="relative">
          <Filter className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-500" />
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="appearance-none rounded-lg border border-gray-700 bg-gray-900 py-2.5 pl-8 pr-8 text-sm text-gray-300 outline-none transition-colors focus:border-accent/50"
          >
            <option value="all">All types</option>
            {ruleTypes.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-accent-dark"
        >
          <Plus className="h-4 w-4" />
          New Rule
        </button>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-lg border border-gray-800 bg-gray-900">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-left text-xs font-medium text-gray-500">
              <th className="px-5 py-3">Name</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Pattern</th>
              <th className="px-4 py-3">Severity</th>
              <th className="px-4 py-3">Action</th>
              <th className="px-4 py-3 text-center">Status</th>
              <th className="px-4 py-3 text-right">Hits</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((rule) => (
              <tr
                key={rule.id}
                className="border-b border-gray-800/50 last:border-0 hover:bg-gray-850"
              >
                <td className="px-5 py-3.5">
                  <div className="flex items-center gap-2 font-medium text-gray-100">
                    {rule.built_in && (
                      <Lock className="h-3.5 w-3.5 flex-shrink-0 text-gray-500" />
                    )}
                    {rule.name}
                  </div>
                </td>
                <td className="px-4 py-3.5">
                  <span className="inline-flex items-center rounded-md bg-gray-800 px-2 py-0.5 text-xs font-medium capitalize text-gray-300">
                    {rule.type}
                  </span>
                </td>
                <td className="max-w-48 truncate px-4 py-3.5 font-mono text-xs text-gray-400">
                  {rule.pattern}
                </td>
                <td className="px-4 py-3.5">
                  <SeverityBadge severity={rule.severity} />
                </td>
                <td className="px-4 py-3.5">
                  <span
                    className={cn(
                      "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium capitalize",
                      rule.action === "block"
                        ? "bg-accent/10 text-accent"
                        : rule.action === "warn"
                          ? "bg-amber-400/10 text-amber-400"
                          : "bg-gray-800 text-gray-400",
                    )}
                  >
                    {rule.action}
                  </span>
                </td>
                <td className="px-4 py-3.5 text-center">
                  <button
                    onClick={() => toggleEnabled(rule.id)}
                    className={cn(
                      "relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full transition-colors",
                      rule.enabled ? "bg-emerald-500" : "bg-gray-700",
                    )}
                  >
                    <span
                      className={cn(
                        "mt-0.5 inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform",
                        rule.enabled ? "translate-x-4.5" : "translate-x-0.5",
                      )}
                    />
                  </button>
                </td>
                <td className="px-4 py-3.5 text-right font-mono text-gray-300">
                  {formatNumber(rule.hit_count)}
                </td>
                <td className="px-4 py-3.5">
                  {!rule.built_in && (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => openEdit(rule)}
                        className="rounded-md p-1.5 text-gray-500 transition-colors hover:bg-gray-800 hover:text-gray-300"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => handleDelete(rule.id)}
                        className="rounded-md p-1.5 text-gray-500 transition-colors hover:bg-accent/10 hover:text-accent"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td
                  colSpan={8}
                  className="px-5 py-8 text-center text-sm text-gray-500"
                >
                  No rules match your search
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="rule-modal-title">
          <div className="w-full max-w-lg rounded-xl border border-gray-700 bg-gray-900 p-6 shadow-2xl">
            <div className="mb-5 flex items-center justify-between">
              <h3 id="rule-modal-title" className="text-base font-semibold text-gray-50">
                {editingId ? "Edit Rule" : "Create Rule"}
              </h3>
              <button
                onClick={() => setModalOpen(false)}
                className="rounded-md p-1 text-gray-500 transition-colors hover:bg-gray-800 hover:text-gray-300"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium text-gray-400">
                  Name
                </label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, name: e.target.value }))
                  }
                  className="w-full rounded-lg border border-gray-700 bg-gray-850 px-3 py-2 text-sm text-gray-100 outline-none focus:border-accent/50"
                />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-gray-400">
                    Type
                  </label>
                  <select
                    value={form.type}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, type: e.target.value }))
                    }
                    className="w-full rounded-lg border border-gray-700 bg-gray-850 px-3 py-2 text-sm text-gray-100 outline-none focus:border-accent/50"
                  >
                    {ruleTypes.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-gray-400">
                    Severity
                  </label>
                  <select
                    value={form.severity}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, severity: e.target.value }))
                    }
                    className="w-full rounded-lg border border-gray-700 bg-gray-850 px-3 py-2 text-sm text-gray-100 outline-none focus:border-accent/50"
                  >
                    {severities.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-gray-400">
                    Action
                  </label>
                  <select
                    value={form.action}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, action: e.target.value }))
                    }
                    className="w-full rounded-lg border border-gray-700 bg-gray-850 px-3 py-2 text-sm text-gray-100 outline-none focus:border-accent/50"
                  >
                    {actionTypes.map((a) => (
                      <option key={a} value={a}>
                        {a}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium text-gray-400">
                  Pattern
                </label>
                <input
                  type="text"
                  value={form.pattern}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, pattern: e.target.value }))
                  }
                  className="w-full rounded-lg border border-gray-700 bg-gray-850 px-3 py-2 font-mono text-sm text-gray-100 outline-none focus:border-accent/50"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium text-gray-400">
                  Description
                </label>
                <textarea
                  value={form.description}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, description: e.target.value }))
                  }
                  rows={2}
                  className="w-full resize-none rounded-lg border border-gray-700 bg-gray-850 px-3 py-2 text-sm text-gray-100 outline-none focus:border-accent/50"
                />
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => setModalOpen(false)}
                className="rounded-lg border border-gray-700 px-4 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-gray-800"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={!form.name || !form.pattern}
                className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-dark disabled:opacity-40"
              >
                {editingId ? "Update" : "Create"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
