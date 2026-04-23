import { useState, useEffect } from "react";
import { SeverityBadge } from "../components/SeverityBadge";
import { cn, formatNumber } from "../lib/utils";
import {
  fetchRules,
  createRule,
  updateRule,
  deleteRule as apiDeleteRule,
  fetchRulePacks,
  installRulePack,
} from "../lib/api";
import type { Rule, RulePackSummary } from "../lib/api";
import { MaterialIcon } from "../components/MaterialIcon";

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
  const [packs, setPacks] = useState<RulePackSummary[]>([]);
  const [installingPack, setInstallingPack] = useState<string | null>(null);
  const [packResult, setPackResult] = useState<{ id: string; installed: number; skipped: number } | null>(null);

  useEffect(() => {
    loadRules();
    fetchRulePacks().then(setPacks).catch(() => {});
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

  async function handleInstallPack(packId: string) {
    setInstallingPack(packId);
    setPackResult(null);
    try {
      const result = await installRulePack(packId);
      setPackResult({ id: packId, installed: result.installed, skipped: result.skipped });
      if (result.installed > 0) {
        await loadRules();
      }
    } catch {
      setPackResult(null);
    } finally {
      setInstallingPack(null);
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
    <div className="space-y-8">
      {/* Header Section */}
      <section className="flex justify-between items-end">
        <div>
          <h1 className="text-4xl font-extrabold tracking-tight text-gray-50">
            Audit Rules Management
          </h1>
          <p className="text-gray-500 mt-2 font-medium">
            Configure safety triggers and thresholds for active AI models.
          </p>
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 px-6 py-3 bg-gradient-to-br from-accent-light to-accent text-gray-50 font-bold rounded-lg hover:opacity-90 transition-all active:scale-95 shadow-lg shadow-accent/10"
        >
          <MaterialIcon icon="add" className="text-lg" />
          <span>Create Rule</span>
        </button>
      </section>

      {/* Search & Filter */}
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
            className="w-full rounded-lg border-none bg-gray-900 py-2.5 pl-10 pr-4 text-sm text-gray-100 placeholder-gray-500 outline-none transition-colors focus:ring-1 focus:ring-accent/30"
          />
        </div>
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          className="appearance-none rounded-lg border-none bg-gray-900 py-2.5 px-4 text-sm text-gray-300 outline-none transition-colors focus:ring-1 focus:ring-accent/30"
        >
          <option value="all">All types</option>
          {ruleTypes.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>

      {/* Table */}
      <div className="bg-gray-900 rounded-xl border border-gray-800/10 overflow-hidden shadow-2xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-gray-950/50 border-b border-gray-800/10">
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
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-gray-800 rounded text-accent">
                        <MaterialIcon icon="shield" className="text-lg" />
                      </div>
                      <div>
                        <div className="text-sm font-bold text-gray-100">{rule.name}</div>
                        {rule.built_in && (
                          <div className="text-[10px] text-gray-500">PROTECTED SYSTEM RULE</div>
                        )}
                      </div>
                      {rule.built_in && (
                        <MaterialIcon
                          icon="lock"
                          className="text-sm text-gray-500/40"
                        />
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span className="px-2 py-1 bg-gray-800 text-gray-300 text-[10px] font-bold rounded-full">
                      {rule.type}
                    </span>
                  </td>
                  <td className="max-w-48 px-6 py-4">
                    <code className="text-xs font-mono text-gray-400 bg-gray-950 px-2 py-1 rounded truncate block">
                      {rule.pattern}
                    </code>
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

      {/* Rule Template Packs */}
      {packs.length > 0 && (
        <div className="bg-gray-900 rounded-xl border border-gray-800/10 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-800/10">
            <h4 className="font-bold tracking-tight text-gray-50">Rule Template Packs</h4>
            <p className="text-xs text-gray-500 mt-1">Pre-built safety rule collections — install with one click</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-6">
            {packs.map((pack) => (
              <div key={pack.id} data-testid={`pack-${pack.id}`} className="bg-gray-950 rounded-xl p-5 flex flex-col">
                <div className="flex items-center gap-2 mb-2">
                  <span className="px-2 py-0.5 bg-gray-800 text-gray-400 text-[10px] font-bold rounded-full uppercase">
                    {pack.category}
                  </span>
                  <span className="text-[10px] text-gray-500">{pack.rule_count} rules</span>
                </div>
                <h5 className="text-sm font-bold text-gray-100 mb-1">{pack.name}</h5>
                <p className="text-[10px] text-gray-500 flex-1 mb-4">{pack.description}</p>
                <button
                  onClick={() => handleInstallPack(pack.id)}
                  disabled={installingPack === pack.id}
                  data-testid={`install-${pack.id}`}
                  className="w-full px-3 py-2 text-xs font-bold bg-accent/15 text-accent rounded-lg hover:bg-accent/25 transition-colors disabled:opacity-40"
                >
                  {installingPack === pack.id
                    ? "Installing..."
                    : packResult?.id === pack.id
                      ? `${packResult.installed} installed, ${packResult.skipped} skipped`
                      : "Install Pack"}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

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
