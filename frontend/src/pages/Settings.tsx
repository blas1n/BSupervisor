import { useState, useEffect } from "react";
import {
  fetchSettings,
  updateSettings,
} from "../lib/api";
import type { ConnectionSettings } from "../lib/api";
import { MaterialIcon } from "../components/MaterialIcon";
import { cn } from "../lib/utils";

const emptyConnections: ConnectionSettings = {
  bsnexus_url: "",
  bsnexus_api_key: "",
  bsgateway_url: "",
  bsage_url: "",
  telegram_bot_token: "",
  slack_webhook_url: "",
};

interface TestResult {
  key: string;
  status: "idle" | "testing" | "success" | "error";
  message?: string;
}

export function Settings() {
  const [form, setForm] = useState<ConnectionSettings>(emptyConnections);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({});

  useEffect(() => {
    loadSettings();
  }, []);

  async function loadSettings() {
    try {
      const data = await fetchSettings();
      setForm(data.connections);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      await updateSettings(form);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  function updateField(key: keyof ConnectionSettings, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function testConnection(key: string, url: string) {
    if (!url) return;
    setTestResults((prev) => ({
      ...prev,
      [key]: { key, status: "testing" },
    }));

    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 5000);
      const response = await fetch(url.replace(/\/$/, "") + "/health", {
        method: "GET",
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (response.ok) {
        setTestResults((prev) => ({
          ...prev,
          [key]: { key, status: "success", message: "Connected" },
        }));
      } else {
        setTestResults((prev) => ({
          ...prev,
          [key]: { key, status: "error", message: `HTTP ${response.status}` },
        }));
      }
    } catch {
      setTestResults((prev) => ({
        ...prev,
        [key]: { key, status: "error", message: "Connection failed" },
      }));
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

  return (
    <div className="space-y-8 max-w-3xl">
      {/* Header */}
      <section>
        <h1 className="text-4xl font-extrabold tracking-tight text-gray-50">
          Settings
        </h1>
        <p className="text-gray-500 mt-2 font-medium">
          Configure connections to external services and notification channels.
        </p>
      </section>

      {/* BSNexus Connection */}
      <SettingsCard
        icon="hub"
        title="BSNexus Connection"
        description="AI orchestration platform for managing agent workflows."
      >
        <FieldGroup>
          <Field
            label="URL"
            value={form.bsnexus_url}
            onChange={(v) => updateField("bsnexus_url", v)}
            placeholder="https://nexus.bsvibe.dev"
          />
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <Field
                label="API Key"
                value={form.bsnexus_api_key}
                onChange={(v) => updateField("bsnexus_api_key", v)}
                placeholder="sk-..."
                type="password"
              />
            </div>
            <TestButton
              result={testResults["bsnexus"]}
              onClick={() => testConnection("bsnexus", form.bsnexus_url)}
              disabled={!form.bsnexus_url}
            />
          </div>
        </FieldGroup>
      </SettingsCard>

      {/* BSGateway Connection */}
      <SettingsCard
        icon="router"
        title="BSGateway Connection"
        description="API gateway and proxy layer for routing agent traffic."
      >
        <FieldGroup>
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <Field
                label="URL"
                value={form.bsgateway_url}
                onChange={(v) => updateField("bsgateway_url", v)}
                placeholder="https://gateway.bsvibe.dev"
              />
            </div>
            <TestButton
              result={testResults["bsgateway"]}
              onClick={() => testConnection("bsgateway", form.bsgateway_url)}
              disabled={!form.bsgateway_url}
            />
          </div>
        </FieldGroup>
      </SettingsCard>

      {/* BSage Connection */}
      <SettingsCard
        icon="psychology"
        title="BSage Connection"
        description="Knowledge and reasoning engine for advanced agent capabilities."
      >
        <FieldGroup>
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <Field
                label="URL"
                value={form.bsage_url}
                onChange={(v) => updateField("bsage_url", v)}
                placeholder="https://sage.bsvibe.dev"
              />
            </div>
            <TestButton
              result={testResults["bsage"]}
              onClick={() => testConnection("bsage", form.bsage_url)}
              disabled={!form.bsage_url}
            />
          </div>
        </FieldGroup>
      </SettingsCard>

      {/* Notification Channels */}
      <SettingsCard
        icon="notifications"
        title="Notification Channels"
        description="Configure where to send alerts and notifications."
      >
        <FieldGroup>
          <Field
            label="Telegram Bot Token"
            value={form.telegram_bot_token}
            onChange={(v) => updateField("telegram_bot_token", v)}
            placeholder="123456:ABC-DEF..."
            type="password"
          />
          <Field
            label="Slack Webhook URL"
            value={form.slack_webhook_url}
            onChange={(v) => updateField("slack_webhook_url", v)}
            placeholder="https://hooks.slack.com/services/..."
          />
        </FieldGroup>
      </SettingsCard>

      {/* Save bar */}
      <div className="flex items-center gap-4">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-6 py-3 bg-gradient-to-br from-accent-light to-accent text-gray-50 font-bold rounded-lg hover:opacity-90 transition-all active:scale-95 shadow-lg shadow-accent/10 disabled:opacity-40"
        >
          <MaterialIcon icon={saving ? "progress_activity" : "save"} className={cn("text-lg", saving && "animate-spin")} />
          <span>{saving ? "Saving..." : "Save Settings"}</span>
        </button>

        {saved && (
          <span className="flex items-center gap-1.5 text-sm font-medium text-success">
            <MaterialIcon icon="check_circle" className="text-lg" filled />
            Settings saved
          </span>
        )}

        {error && (
          <span className="flex items-center gap-1.5 text-sm font-medium text-accent">
            <MaterialIcon icon="error" className="text-lg" filled />
            {error}
          </span>
        )}
      </div>
    </div>
  );
}

/* --- Sub-components --- */

function SettingsCard({
  icon,
  title,
  description,
  children,
}: {
  icon: string;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-gray-800/10 bg-gray-900 p-6 shadow-2xl">
      <div className="mb-5 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent/10">
          <MaterialIcon icon={icon} className="text-xl text-accent" />
        </div>
        <div>
          <h2 className="text-base font-bold tracking-tight text-gray-50">
            {title}
          </h2>
          <p className="text-xs text-gray-500">{description}</p>
        </div>
      </div>
      {children}
    </div>
  );
}

function FieldGroup({ children }: { children: React.ReactNode }) {
  return <div className="space-y-4">{children}</div>;
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <div>
      <label className="mb-1.5 block text-[10px] uppercase font-bold tracking-widest text-gray-400">
        {label}
      </label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-xl border border-gray-800/40 bg-gray-850 px-3 py-2 text-sm text-gray-100 placeholder-gray-600 outline-none transition-colors focus:border-accent/50"
      />
    </div>
  );
}

function TestButton({
  result,
  onClick,
  disabled,
}: {
  result?: TestResult;
  onClick: () => void;
  disabled: boolean;
}) {
  const status = result?.status ?? "idle";
  const isTesting = status === "testing";

  return (
    <button
      onClick={onClick}
      disabled={disabled || isTesting}
      className={cn(
        "mb-px flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-medium transition-colors",
        status === "success"
          ? "border-success/30 bg-success/10 text-success"
          : status === "error"
            ? "border-accent/30 bg-accent/10 text-accent"
            : "border-gray-800/40 bg-gray-850 text-gray-400 hover:text-gray-200 hover:border-gray-700",
        (disabled || isTesting) && "opacity-40 cursor-not-allowed",
      )}
      title={result?.message}
    >
      <MaterialIcon
        icon={
          status === "testing"
            ? "progress_activity"
            : status === "success"
              ? "check_circle"
              : status === "error"
                ? "error"
                : "link"
        }
        className={cn("text-sm", isTesting && "animate-spin")}
      />
      <span>Test</span>
    </button>
  );
}
