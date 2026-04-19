import { useState, useEffect } from "react";
import { cn, formatTime } from "../lib/utils";
import { fetchIncidents, fetchIncident, resolveIncident } from "../lib/api";
import type { IncidentListItem, IncidentDetail } from "../lib/api";
import { SeverityBadge } from "../components/SeverityBadge";
import { MaterialIcon } from "../components/MaterialIcon";

export function Incidents() {
  const [incidents, setIncidents] = useState<IncidentListItem[]>([]);
  const [selected, setSelected] = useState<IncidentDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchIncidents()
      .then(setIncidents)
      .finally(() => setLoading(false));
  }, []);

  async function handleSelect(id: string) {
    const detail = await fetchIncident(id);
    setSelected(detail);
  }

  async function handleResolve(id: string) {
    await resolveIncident(id);
    setIncidents((prev) =>
      prev.map((inc) => (inc.id === id ? { ...inc, status: "resolved" } : inc)),
    );
    if (selected?.id === id) {
      setSelected({ ...selected, status: "resolved" });
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <MaterialIcon icon="progress_activity" className="animate-spin text-gray-500 text-3xl" />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-bold tracking-tight text-gray-50">Incident Timeline</h3>
          <p className="text-xs text-gray-400">Forensic view of blocked events grouped by agent</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Incident List */}
        <div className="lg:col-span-1 bg-gray-900 rounded-2xl overflow-hidden flex flex-col max-h-[700px]">
          <div className="px-6 py-4 border-b border-gray-800/10">
            <h4 className="text-sm font-bold text-gray-50">Incidents ({incidents.length})</h4>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {incidents.length === 0 ? (
              <p className="py-8 text-center text-sm text-gray-500">No incidents detected</p>
            ) : (
              incidents.map((inc) => (
                <button
                  key={inc.id}
                  onClick={() => handleSelect(inc.id)}
                  data-testid={`incident-${inc.id}`}
                  className={cn(
                    "w-full text-left p-4 rounded-xl transition-colors",
                    selected?.id === inc.id ? "bg-gray-800" : "bg-gray-950 hover:bg-gray-800/50",
                  )}
                >
                  <div className="flex items-center justify-between mb-1">
                    <SeverityBadge severity={inc.severity} />
                    <span
                      className={cn(
                        "text-[10px] font-bold uppercase px-2 py-0.5 rounded-full",
                        inc.status === "open"
                          ? "bg-accent/15 text-accent"
                          : "bg-success/15 text-success",
                      )}
                    >
                      {inc.status}
                    </span>
                  </div>
                  <p className="text-xs font-medium text-gray-100 truncate mt-1">{inc.title}</p>
                  <div className="flex items-center gap-3 mt-2 text-[10px] text-gray-500">
                    <span>{inc.agent_id}</span>
                    <span>|</span>
                    <span>{inc.event_count} events</span>
                    <span>|</span>
                    <span>{formatTime(inc.started_at)}</span>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Incident Detail + Timeline */}
        <div className="lg:col-span-2 bg-gray-900 rounded-2xl overflow-hidden flex flex-col max-h-[700px]">
          {selected ? (
            <>
              <div className="px-6 py-4 border-b border-gray-800/10 flex items-center justify-between">
                <div>
                  <h4 className="text-sm font-bold text-gray-50">{selected.title}</h4>
                  <p className="text-[10px] text-gray-500 mt-1">
                    Agent: {selected.agent_id} &bull; {selected.event_count} events &bull;{" "}
                    {formatTime(selected.started_at)} &mdash; {formatTime(selected.updated_at)}
                  </p>
                </div>
                {selected.status === "open" && (
                  <button
                    onClick={() => handleResolve(selected.id)}
                    data-testid="resolve-btn"
                    className="px-4 py-2 text-xs font-bold bg-success/15 text-success rounded-lg hover:bg-success/25 transition-colors"
                  >
                    Resolve
                  </button>
                )}
              </div>
              <div className="flex-1 overflow-y-auto p-6">
                <div className="relative">
                  {/* Vertical line */}
                  <div className="absolute left-4 top-0 bottom-0 w-px bg-gray-800" />
                  <div className="space-y-4">
                    {selected.timeline.map((entry) => (
                      <div key={entry.id} className="flex items-start gap-4 pl-2">
                        <div
                          className={cn(
                            "w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 z-10 ring-4 ring-gray-900",
                            entry.allowed ? "bg-success" : "bg-accent",
                          )}
                        >
                          <MaterialIcon
                            icon={entry.allowed ? "check" : "close"}
                            className="text-[10px] text-white"
                          />
                        </div>
                        <div className="flex-1 bg-gray-950 rounded-xl p-4">
                          <div className="flex items-center justify-between mb-1">
                            <span
                              data-testid="timeline-entry"
                              className={cn(
                                "text-[10px] font-bold uppercase",
                                entry.allowed ? "text-success" : "text-accent",
                              )}
                            >
                              {entry.allowed ? "Allowed" : "Blocked"}
                            </span>
                            <span className="text-[10px] text-gray-500">
                              {formatTime(entry.timestamp)}
                            </span>
                          </div>
                          <p className="text-xs font-medium text-gray-100">{entry.event_type}: {entry.action}</p>
                          <p className="text-[10px] text-gray-500 mt-1 break-all">{entry.target}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-gray-500">
              <div className="text-center">
                <MaterialIcon icon="timeline" className="text-4xl mb-3 opacity-30" />
                <p className="text-sm">Select an incident to view its timeline</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
