"use client";

import { useCallback, useEffect, useState } from "react";
import {
  DATABASE_ENGINES,
  ProjectDatabase,
  DatabaseEngine,
  listProjectDatabases,
  provisionDatabase,
  deleteDatabase,
  rotateDatabase,
  refreshDatabaseStatus,
} from "@/lib/api";

const STATUS_STYLES: Record<string, string> = {
  ready: "text-green-400 border-green-800/60 bg-green-900/20",
  creating: "text-[#c8f135] border-[#c8f135]/40 bg-[#c8f135]/10 animate-pulse",
  failed: "text-red-400 border-red-800/60 bg-red-900/20",
  deprovisioned: "text-gray-500 border-[#2a2a2a] bg-[#1a1a1a]",
  unknown: "text-gray-400 border-[#2a2a2a] bg-[#1a1a1a]",
};

function StatusPill({ status }: { status: string }) {
  return (
    <span
      className={`text-[11px] font-mono px-2 py-0.5 rounded-full border ${STATUS_STYLES[status] ?? STATUS_STYLES.unknown}`}
    >
      {status}
    </span>
  );
}

const ENGINE_COLORS: Record<string, string> = {
  postgres: "text-sky-400 border-sky-800/60",
  mongo: "text-green-400 border-green-800/60",
  redis: "text-red-400 border-red-800/60",
};

export default function DatabasePanel({ projectId }: { projectId: string }) {
  const [databases, setDatabases] = useState<ProjectDatabase[]>([]);
  const [loading, setLoading] = useState(true);
  const [provisioning, setProvisioning] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [selectedEngine, setSelectedEngine] = useState<DatabaseEngine>("postgres");
  const [fullUrl, setFullUrl] = useState<string | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const docs = await listProjectDatabases(projectId);
      setDatabases(docs);
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load databases");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleProvision() {
    setError("");
    setFullUrl(null);
    setProvisioning(true);
    try {
      const result = await provisionDatabase(projectId, { engine: selectedEngine });
      setFullUrl(
        result.connection_external || result.connection_internal
      );
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to provision database");
    } finally {
      setProvisioning(false);
    }
  }

  async function handleRefresh(database_id: string) {
    setError("");
    setBusyId(database_id);
    try {
      await refreshDatabaseStatus(projectId, database_id);
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Status refresh failed");
    } finally {
      setBusyId(null);
    }
  }

  async function handleRotate(database_id: string) {
    setError("");
    setFullUrl(null);
    setBusyId(database_id);
    try {
      const result = await rotateDatabase(projectId, database_id);
      setFullUrl(result.connection_external || result.connection_internal);
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Credential rotation failed");
    } finally {
      setBusyId(null);
    }
  }

  async function handleDeprovision(database_id: string) {
    setError("");
    setBusyId(database_id);
    try {
      await deleteDatabase(projectId, database_id);
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to deprovision database");
    } finally {
      setBusyId(null);
    }
  }

  const active = databases.filter((d) => d.status !== "deprovisioned");

  return (
    <div className="bg-[#161616] border border-[#2a2a2a] rounded-2xl p-6">
      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <h2 className="font-mono font-bold text-white text-sm uppercase tracking-wider">
          Managed Databases
        </h2>
        <StatusPill status={active.length > 0 ? `${active.length} active` : "0 active"} />
      </div>

      {error && (
        <p className="mb-4 text-xs text-red-400 bg-red-900/20 border border-red-900/40 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {fullUrl && (
        <div className="mb-4 p-3 bg-[#c8f135]/5 border border-[#c8f135]/30 rounded-xl">
          <p className="text-[11px] font-mono text-[#c8f135] mb-1">
            New connection string (shown once — also exported to your app as a
            reserved environment variable)
          </p>
          <code className="text-xs text-gray-200 break-all select-all">
            {fullUrl}
          </code>
        </div>
      )}

      {loading ? (
        <div className="space-y-3 animate-pulse">
          <div className="h-14 bg-[#1a1a1a] rounded-xl" />
          <div className="h-14 bg-[#1a1a1a] rounded-xl" />
        </div>
      ) : databases.length === 0 ? (
        <p className="text-sm text-gray-500 mb-5">
          No databases yet. Provision one below — it gets deployed inside the
          cluster and its connection string is injected into your app.
        </p>
      ) : (
        <ul className="space-y-3 mb-5">
          {databases.map((db) => (
            <li
              key={db.database_id}
              className="border border-[#2a2a2a] rounded-xl p-3 flex flex-col sm:flex-row sm:items-center gap-3"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span
                    className={`font-mono text-xs font-bold border px-2 py-0.5 rounded-md ${ENGINE_COLORS[db.engine]}`}
                  >
                    {db.engine}
                  </span>
                  <StatusPill status={db.status} />
                  <span className="text-xs text-gray-500 font-mono">
                    {db.size_gb}Gi
                  </span>
                </div>
                <p className="text-[11px] text-gray-600 font-mono mt-1">
                  {db.database_id}
                </p>
                {db.status === "ready" && db.connection_url && (
                  <p className="text-[11px] text-gray-500 font-mono mt-1 truncate">
                    {db.connection_url}
                  </p>
                )}
              </div>

              <div className="flex items-center gap-2 shrink-0">
                {db.status === "ready" && (
                  <button
                    onClick={() => handleRotate(db.database_id)}
                    disabled={busyId === db.database_id}
                    className="text-[11px] font-mono px-2.5 py-1.5 rounded-lg border border-[#2a2a2a] text-gray-400 hover:text-gray-200 hover:border-[#3a3a3a] transition-colors disabled:opacity-50"
                  >
                    {busyId === db.database_id ? "…" : "Rotate creds"}
                  </button>
                )}
                {db.status !== "deprovisioned" && (
                  <button
                    onClick={() => handleDeprovision(db.database_id)}
                    disabled={busyId === db.database_id}
                    className="text-[11px] font-mono px-2.5 py-1.5 rounded-lg border border-red-900/40 text-red-400 hover:bg-red-900/20 transition-colors disabled:opacity-50"
                  >
                    {busyId === db.database_id ? "…" : "Deprovision"}
                  </button>
                )}
                {db.status === "creating" && (
                  <button
                    onClick={() => handleRefresh(db.database_id)}
                    disabled={busyId === db.database_id}
                    className="text-[11px] font-mono px-2.5 py-1.5 rounded-lg border border-[#2a2a2a] text-gray-400 hover:text-gray-200 transition-colors disabled:opacity-50"
                  >
                    Refresh
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {active.length < 2 && (
        <div className="border-t border-[#2a2a2a] pt-5">
          <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center">
            <div className="flex gap-2">
              {DATABASE_ENGINES.map((engine) => (
                <button
                  key={engine.value}
                  onClick={() => setSelectedEngine(engine.value)}
                  disabled={provisioning}
                  className={`text-xs font-mono px-3 py-2 rounded-xl border transition-colors disabled:opacity-50 ${
                    selectedEngine === engine.value
                      ? "border-[#c8f135] text-[#c8f135] bg-[#c8f135]/10"
                      : "border-[#2a2a2a] text-gray-400 hover:border-[#3a3a3a]"
                  }`}
                >
                  {engine.label}
                </button>
              ))}
            </div>
            <button
              onClick={handleProvision}
              disabled={provisioning}
              className="flex-1 sm:flex-none font-mono font-bold text-sm px-5 py-2.5 rounded-xl bg-[#c8f135] hover:bg-[#d8f35a] text-black transition-colors disabled:opacity-50"
            >
              {provisioning ? "Provisioning…" : "＋ Provision"}
            </button>
          </div>
          <p className="text-[11px] text-gray-600 mt-3">
            {DATABASE_ENGINES.find((e) => e.value === selectedEngine)?.description} ·
            One database per engine per project. A second attempt on a ready
            database rotates its credentials instead of creating a duplicate.
          </p>
        </div>
      )}
    </div>
  );
}