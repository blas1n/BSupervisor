import { useState, useEffect } from "react";
import { SeverityBadge } from "../components/SeverityBadge";
import { cn, formatNumber } from "../lib/utils";
import {
  fetchRules,
  createRule,
  updateRule,
  deleteRule as apiDeleteRule,
} from "../lib/api";
import type { Rule } from "../lib/api";

function MaterialIcon({
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
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filterType, setFilterType] = useState<string>("all");
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<RuleFormData>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    loadRules();
  }, []);

  async function loadRules() {
    try {
      const data = await fetchRules();
      setRules(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load rules");
    } finally {
      setLoading(false);
    }
  }

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
    setSaveError(null);
    setModalOpen(true);
  }

  function openEdit(rule: Rule) {
    setSaveError(null);
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

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    try {
      if (editingId) {
        const updated = await updateRule(editingId, form);
        setRules((prev) => prev.map((r) => (r.id === editingId ? updated : r)));
      } else {
        const created = await createRule(form);
        setRules((prev) => [...prev, created]);
      }
      setModalOpen(false);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save rule");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    const prev = rules;
    setRules((r) => r.filter((rule) => rule.id !== id));
    try {
      await apiDeleteRule(id);
    } catch {
      setRules(prev);
    }
  }

  async function toggleEnabled(id: string) {
    const rule = rules.find((r) => r.id === id);
    if (!rule) return;
    const prev = rules;
    setRules((r) => r.map((item) => (item.id === id ? { ...item, enabled: !item.enabled } : item)));
    try {
      await updateRule(id, { enabled: !rule.enabled });
    } catch {
      setRules(prev);
    }
  }

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

  return (
    <div className="space-y-6">
      {/* Toolbar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <MaterialIcon
            icon="search"
            className="absolute left-3 top-1/2 -translate-y-1/2 text-lg text-gray-500"
          />
          <input
            type="text"
            placeholder="Search rules by name or pattern..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-xl border border-gray-800/40 bg-gray-900 py-2.5 pl-10 pr-4 text-sm text-gray-100 placeholder-gray-500 outline-none transition-colors focus:border-accent/50 focus:ring-1 focus:ring-accent/30"
          />
        </div>
        <div className="relative">
          <MaterialIcon
            icon="filter_list"
            className="absolute left-3 top-1/2 -translate-y-1/2 text-lg text-gray-500"
          />
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="appearance-none rounded-xl border border-gray-800/40 bg-gray-900 py-2.5 pl-10 pr-8 text-sm text-gray-300 outline-none transition-colors focus:border-accent/50"
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
          className="flex items-center gap-2 rounded-xl bg-accent px-4 py-2.5 text-sm font-medium text-gray-50 transition-colors hover:bg-accent-dark"
        >
          <MaterialIcon icon="add" className="text-lg" />
          New Rule
        </button>
      </div>

      {/* Table */}
      <div className="bg-gray-900 rounded-xl border border-gray-800/40 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-gray-950">
              <tr>
                <th className="px-6 py-4 text-[10px] uppercase font-bold tracking-widest text-gray-500">
                  Name
                </th>
                <th className="px-6 py-4 text-[10px] uppercase font-bold tracking-widest text-gray-500">
                  Type
                </th>
                <th className="px-6 py-4 text-[10px] uppercase font-bold tracking-widest text-gray-500">
                  Pattern
                </th>
                <th className="px-6 py-4 text-[10px] uppercase font-bold tracking-widest text-gray-500">
                  Severity
                </th>
                <th className="px-6 py-4 text-[10px] uppercase font-bold tracking-widest text-gray-500">
                  Action
                </th>
                <th className="px-6 py-4 text-[10px] uppercase font-bold tracking-widest text-gray-500 text-center">
                  Status
                </th>
                <th className="px-6 py-4 text-[10px] uppercase font-bold tracking-widest text-gray-500 text-right">
                  Hits
                </th>
                <th className="px-6 py-4"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/30">
              {filtered.map((rule) => (
                <tr
                  key={rule.id}
                  className="hover:bg-gray-850 transition-colors"
                >
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2 font-semibold text-gray-100">
                      {rule.built_in && (
                        <MaterialIcon
                          icon="lock"
                          className="text-sm text-gray-500"
                        />
                      )}
                      <span className="text-sm">{rule.name}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span className="inline-flex items-center rounded-md bg-gray-800 px-2 py-0.5 text-xs font-medium capitalize text-gray-300">
                      {rule.type}
                    </span>
                  </td>
                  <td className="max-w-48 truncate px-6 py-4 font-mono text-xs text-gray-400">
                    {rule.pattern}
                  </td>
                  <td className="px-6 py-4">
                    <SeverityBadge severity={rule.severity} />
                  </td>
                  <td className="px-6 py-4">
                    <span
                      className={cn(
                        "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium capitalize",
                        rule.action === "block"
                          ? "bg-accent/10 text-accent"
                          : rule.action === "warn"
                            ? "bg-warning/10 text-warning"
                            : "bg-gray-800 text-gray-400",
                      )}
                    >
                      {rule.action}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-center">
                    <button
                      onClick={() => toggleEnabled(rule.id)}
                      className={cn(
                        "relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full transition-colors",
                        rule.enabled ? "bg-success" : "bg-gray-700",
                      )}
                    >
                      <span
                        className={cn(
                          "mt-0.5 inline-block h-4 w-4 transform rounded-full bg-gray-50 shadow transition-transform",
                          rule.enabled ? "translate-x-4.5" : "translate-x-0.5",
                        )}
                      />
                    </button>
                  </td>
                  <td className="px-6 py-4 text-right font-mono text-sm text-gray-300">
                    {formatNumber(rule.hit_count)}
                  </td>
                  <td className="px-6 py-4">
                    {!rule.built_in && (
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => openEdit(rule)}
                          className="rounded-md p-1.5 text-gray-500 transition-colors hover:bg-gray-800 hover:text-gray-300"
                        >
                          <MaterialIcon icon="edit" className="text-sm" />
                        </button>
                        <button
                          onClick={() => handleDelete(rule.id)}
                          className="rounded-md p-1.5 text-gray-500 transition-colors hover:bg-accent/10 hover:text-accent"
                        >
                          <MaterialIcon icon="delete" className="text-sm" />
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
                    className="px-6 py-8 text-center text-sm text-gray-500"
                  >
                    {rules.length === 0 ? "No rules configured" : "No rules match your search"}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="rule-modal-title">
          <div className="w-full max-w-lg rounded-xl border border-gray-800/40 bg-gray-900 p-6 shadow-2xl">
            <div className="mb-5 flex items-center justify-between">
              <h3 id="rule-modal-title" className="text-lg font-bold tracking-tight text-gray-50">
                {editingId ? "Edit Rule" : "Create Rule"}
              </h3>
              <button
                onClick={() => setModalOpen(false)}
                className="rounded-md p-1 text-gray-500 transition-colors hover:bg-gray-800 hover:text-gray-300"
              >
                <MaterialIcon icon="close" className="text-lg" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="mb-1.5 block text-[10px] uppercase font-bold tracking-widest text-gray-400">
                  Name
                </label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, name: e.target.value }))
                  }
                  className="w-full rounded-xl border border-gray-800/40 bg-gray-850 px-3 py-2 text-sm text-gray-100 outline-none focus:border-accent/50"
                />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="mb-1.5 block text-[10px] uppercase font-bold tracking-widest text-gray-400">
                    Type
                  </label>
                  <select
                    value={form.type}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, type: e.target.value }))
                    }
                    className="w-full rounded-xl border border-gray-800/40 bg-gray-850 px-3 py-2 text-sm text-gray-100 outline-none focus:border-accent/50"
                  >
                    {ruleTypes.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1.5 block text-[10px] uppercase font-bold tracking-widest text-gray-400">
                    Severity
                  </label>
                  <select
                    value={form.severity}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, severity: e.target.value }))
                    }
                    className="w-full rounded-xl border border-gray-800/40 bg-gray-850 px-3 py-2 text-sm text-gray-100 outline-none focus:border-accent/50"
                  >
                    {severities.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1.5 block text-[10px] uppercase font-bold tracking-widest text-gray-400">
                    Action
                  </label>
                  <select
                    value={form.action}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, action: e.target.value }))
                    }
                    className="w-full rounded-xl border border-gray-800/40 bg-gray-850 px-3 py-2 text-sm text-gray-100 outline-none focus:border-accent/50"
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
                <label className="mb-1.5 block text-[10px] uppercase font-bold tracking-widest text-gray-400">
                  Pattern
                </label>
                <input
                  type="text"
                  value={form.pattern}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, pattern: e.target.value }))
                  }
                  className="w-full rounded-xl border border-gray-800/40 bg-gray-850 px-3 py-2 font-mono text-sm text-gray-100 outline-none focus:border-accent/50"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-[10px] uppercase font-bold tracking-widest text-gray-400">
                  Description
                </label>
                <textarea
                  value={form.description}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, description: e.target.value }))
                  }
                  rows={2}
                  className="w-full resize-none rounded-xl border border-gray-800/40 bg-gray-850 px-3 py-2 text-sm text-gray-100 outline-none focus:border-accent/50"
                />
              </div>
            </div>

            {saveError && (
              <p className="mt-4 text-xs text-accent">{saveError}</p>
            )}
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => setModalOpen(false)}
                className="rounded-xl border border-gray-800/40 px-4 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-gray-800"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={!form.name || !form.pattern || saving}
                className="rounded-xl bg-accent px-4 py-2 text-sm font-medium text-gray-50 transition-colors hover:bg-accent-dark disabled:opacity-40"
              >
                {saving ? "Saving..." : editingId ? "Update" : "Create"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
