"use client";

import { useState, useEffect } from "react";
import { useT } from "@bsvibe/i18n";
import {
  fetchSettings,
  updateSettings,
} from "../lib/api";
import type { ConnectionSettings, IntegrationEntry, IntegrationType } from "../lib/api";
import { MaterialIcon } from "../components/MaterialIcon";
import { cn } from "../lib/utils";

const INTEGRATION_TYPES: { value: IntegrationType; label: string }[] = [
  { value: "bsnexus", label: "BSNexus" },
  { value: "bsgateway", label: "BSGateway" },
  { value: "bsage", label: "BSage" },
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "custom", label: "Custom" },
];

const TYPE_PRESETS: Record<string, { icon: string; defaultUrl: string }> = {
  bsnexus: { icon: "hub", defaultUrl: "https://nexus.bsvibe.dev" },
  bsgateway: { icon: "router", defaultUrl: "https://gateway.bsvibe.dev" },
  bsage: { icon: "psychology", defaultUrl: "https://sage.bsvibe.dev" },
  openai: { icon: "smart_toy", defaultUrl: "https://api.openai.com" },
  anthropic: { icon: "neurology", defaultUrl: "https://api.anthropic.com" },
  custom: { icon: "extension", defaultUrl: "" },
};

function makeId(): string {
  return `int-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

const emptyConnections: ConnectionSettings = {
  integrations: [],
  telegram_bot_token: "",
  slack_webhook_url: "",
};

interface TestResult {
  key: string;
  status: "idle" | "testing" | "success" | "error";
  message?: string;
}

export function Settings() {
  const t = useT("supervisor.settings");
  const [form, setForm] = useState<ConnectionSettings>(emptyConnections);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({});

  useEffect(() => {
    (async () => {
      try {
        const data = await fetchSettings();
        setForm(data.connections);
      } catch (err) {
        // Empty sentinel = "failed without a message"; the i18n fallback
        // is resolved at render so `t` stays out of the effect deps.
        setError(err instanceof Error ? err.message : "");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function handleSave() {
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      await updateSettings(form);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("saveError"));
    } finally {
      setSaving(false);
    }
  }

  function addIntegration() {
    setForm((prev) => ({
      ...prev,
      integrations: [
        ...prev.integrations,
        {
          id: makeId(),
          name: "",
          type: "custom" as IntegrationType,
          endpoint_url: "",
          api_key: "",
        },
      ],
    }));
  }

  function removeIntegration(id: string) {
    setForm((prev) => ({
      ...prev,
      integrations: prev.integrations.filter((i) => i.id !== id),
    }));
  }

  function updateIntegration(id: string, patch: Partial<IntegrationEntry>) {
    setForm((prev) => ({
      ...prev,
      integrations: prev.integrations.map((i) => {
        if (i.id !== id) return i;
        const updated = { ...i, ...patch };
        // Auto-fill URL when type changes and URL is empty or was a preset default
        if (patch.type && patch.type !== i.type) {
          const oldPreset = TYPE_PRESETS[i.type];
          const newPreset = TYPE_PRESETS[patch.type];
          if (!i.endpoint_url || i.endpoint_url === oldPreset?.defaultUrl) {
            updated.endpoint_url = newPreset?.defaultUrl ?? "";
          }
          // Auto-fill name if empty or was a type label
          const oldLabel = INTEGRATION_TYPES.find((t) => t.value === i.type)?.label ?? "";
          if (!i.name || i.name === oldLabel) {
            updated.name = INTEGRATION_TYPES.find((t) => t.value === patch.type)?.label ?? "";
          }
        }
        return updated;
      }),
    }));
  }

  function updateNotification(key: "telegram_bot_token" | "slack_webhook_url", value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function testConnection(integrationId: string, url: string) {
    if (!url) return;
    setTestResults((prev) => ({
      ...prev,
      [integrationId]: { key: integrationId, status: "testing" },
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
          [integrationId]: { key: integrationId, status: "success", message: t("testConnected") },
        }));
      } else {
        setTestResults((prev) => ({
          ...prev,
          [integrationId]: {
            key: integrationId,
            status: "error",
            message: t("testHttpError", { status: response.status }),
          },
        }));
      }
    } catch {
      setTestResults((prev) => ({
        ...prev,
        [integrationId]: { key: integrationId, status: "error", message: t("testFailed") },
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
          {t("heading")}
        </h1>
        <p className="text-gray-500 mt-2 font-medium">
          {t("subtitle")}
        </p>
      </section>

      {/* Agent Platforms */}
      <SettingsCard
        icon="hub"
        title={t("platformsTitle")}
        description={t("platformsDescription")}
      >
        <div className="space-y-4">
          {form.integrations.map((integration) => (
            <IntegrationCard
              key={integration.id}
              integration={integration}
              testResult={testResults[integration.id]}
              onUpdate={(patch) => updateIntegration(integration.id, patch)}
              onRemove={() => removeIntegration(integration.id)}
              onTest={() => testConnection(integration.id, integration.endpoint_url)}
            />
          ))}

          <button
            onClick={addIntegration}
            data-testid="add-integration"
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-gray-700 py-3 text-sm font-medium text-gray-400 transition-colors hover:border-accent/50 hover:text-accent"
          >
            <MaterialIcon icon="add" className="text-lg" />
            <span>{t("addIntegration")}</span>
          </button>
        </div>
      </SettingsCard>

      {/* Notification Channels */}
      <SettingsCard
        icon="notifications"
        title={t("notificationsTitle")}
        description={t("notificationsDescription")}
      >
        <FieldGroup>
          <Field
            label={t("fieldTelegram")}
            value={form.telegram_bot_token}
            onChange={(v) => updateNotification("telegram_bot_token", v)}
            placeholder={t("fieldTelegramPlaceholder")}
            type="password"
          />
          <Field
            label={t("fieldSlack")}
            value={form.slack_webhook_url}
            onChange={(v) => updateNotification("slack_webhook_url", v)}
            placeholder={t("fieldSlackPlaceholder")}
          />
        </FieldGroup>
      </SettingsCard>

      {/* Save bar */}
      <div className="flex items-center gap-4">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-6 py-3 bg-accent text-gray-50 font-bold rounded-lg hover:opacity-90 transition-all active:scale-95 shadow-lg shadow-accent/10 disabled:opacity-40"
        >
          <MaterialIcon icon={saving ? "progress_activity" : "save"} className={cn("text-lg", saving && "animate-spin")} />
          <span>{saving ? t("saving") : t("save")}</span>
        </button>

        {saved && (
          <span className="flex items-center gap-1.5 text-sm font-medium text-success">
            <MaterialIcon icon="check_circle" className="text-lg" filled />
            {t("saved")}
          </span>
        )}

        {error !== null && (
          <span className="flex items-center gap-1.5 text-sm font-medium text-accent">
            <MaterialIcon icon="error" className="text-lg" filled />
            {error || t("loadError")}
          </span>
        )}
      </div>
    </div>
  );
}

/* --- Sub-components --- */

function IntegrationCard({
  integration,
  testResult,
  onUpdate,
  onRemove,
  onTest,
}: {
  integration: IntegrationEntry;
  testResult?: TestResult;
  onUpdate: (patch: Partial<IntegrationEntry>) => void;
  onRemove: () => void;
  onTest: () => void;
}) {
  const t = useT("supervisor.settings");
  const preset = TYPE_PRESETS[integration.type] ?? TYPE_PRESETS.custom;

  return (
    <div className="rounded-xl border border-gray-800/30 bg-gray-850 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/10">
            <MaterialIcon icon={preset.icon} className="text-base text-accent" />
          </div>
          <span className="text-sm font-semibold text-gray-200">
            {integration.name || t("newIntegration")}
          </span>
        </div>
        <button
          onClick={onRemove}
          data-testid="remove-integration"
          className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-gray-500 transition-colors hover:bg-accent/10 hover:text-accent"
        >
          <MaterialIcon icon="delete" className="text-sm" />
          <span>{t("remove")}</span>
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Field
          label={t("fieldName")}
          value={integration.name}
          onChange={(v) => onUpdate({ name: v })}
          placeholder={t("fieldNamePlaceholder")}
        />
        <div>
          <label className="mb-1.5 block text-[10px] uppercase font-bold tracking-widest text-gray-400">
            {t("fieldType")}
          </label>
          <select
            value={integration.type}
            onChange={(e) => onUpdate({ type: e.target.value as IntegrationType })}
            className="min-h-10 w-full rounded-xl border border-gray-800/40 bg-gray-850 px-3 py-2 text-sm text-gray-100 outline-none transition-colors focus:border-accent/50"
          >
            {INTEGRATION_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex items-end gap-2">
        <div className="flex-1">
          <Field
            label={t("fieldEndpoint")}
            value={integration.endpoint_url}
            onChange={(v) => onUpdate({ endpoint_url: v })}
            placeholder={preset.defaultUrl || t("fieldEndpointPlaceholder")}
          />
        </div>
        <TestButton
          result={testResult}
          onClick={onTest}
          disabled={!integration.endpoint_url}
        />
      </div>

      <Field
        label={t("fieldApiKey")}
        value={integration.api_key}
        onChange={(v) => onUpdate({ api_key: v })}
        placeholder={t("fieldApiKeyPlaceholder")}
        type="password"
      />
    </div>
  );
}

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
        className="min-h-10 w-full rounded-xl border border-gray-800/40 bg-gray-850 px-3 py-2 text-sm text-gray-100 placeholder-gray-600 outline-none transition-colors focus:border-accent/50"
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
  const t = useT("supervisor.settings");
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
      <span>{t("test")}</span>
    </button>
  );
}
