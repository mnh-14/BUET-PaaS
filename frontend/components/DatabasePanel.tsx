"use client";

import { useCallback, useEffect, useState } from "react";
import {
  DATABASE_ENGINES,
  DatabaseEngine,
  DatabaseEnginesResponse,
  DatabaseLogs,
  StandaloneDatabase,
  getDatabaseEngines,
  getDatabaseLogs,
  listDatabases,
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
  mongodb: "text-green-400 border-green-800/60",
  mysql: "text-orange-400 border-orange-800/60",
  redis: "text-red-400 border-red-800/60",
};

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-[11px] font-mono text-gray-500 uppercase tracking-wider">
        {label}
      </span>
      {children}
    </label>
  );
}

const inputClass =
  "w-full mt-1 bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg px-3 py-2 text-sm text-gray-200 font-mono focus:outline-none focus:border-[#c8f135]/60";

export default function DatabasePanel() {
  const [databases, setDatabases] = useState<StandaloneDatabase[]>([]);
  const [engines, setEngines] = useState<DatabaseEnginesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [provisioning, setProvisioning] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [logsFor, setLogsFor] = useState<string | null>(null);
  const [logs, setLogs] = useState<DatabaseLogs | null>(null);
  const [logsLoading, setLogsLoading] = useState(false);

  const [engine, setEngine] = useState<DatabaseEngine>("postgres");
  const [dbName, setDbName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [sizeGb, setSizeGb] = useState<number | "">(1);
  const [host, setHost] = useState("");
  const [port, setPort] = useState<number | "">("");
  const [storageClass, setStorageClass] = useState("");
  const [external, setExternal] = useState(true);

  const [fullUrl, setFullUrl] = useState<string | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [docs, info] = await Promise.all([
        listDatabases(),
        getDatabaseEngines(),
      ]);
      setDatabases(docs);
      setEngines(info);
      setHost((current) => current || info.external_host);
      setStorageClass((current) => current || info.default_storage_class);
      if (info.engines.postgres) {
        setPort(
          (current) => current || (info.engines.postgres?.default_port ?? 5432)
        );
      }
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load databases");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function onEngineChange(value: DatabaseEngine) {
    setEngine(value);
    setPort(engines?.engines[value]?.default_port ?? "");
  }

  async function handleProvision() {
    setError("");
    setFullUrl(null);
    if (!dbName.trim()) {
      setError("A database name is required.");
      return;
    }
    setProvisioning(true);
    try {
      const result = await provisionDatabase({
        engine,
        db_name: dbName.trim().toLowerCase(),
        username: username.trim() || undefined,
        password: password || undefined,
        size_gb: sizeGb === "" ? undefined : Number(sizeGb),
        host: host.trim() || undefined,
        port: port === "" ? undefined : Number(port),
        storage_class: storageClass.trim() || undefined,
        external,
      });
      setFullUrl(result.connection_external || result.connection_internal);
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
      await refreshDatabaseStatus(database_id);
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
      const result = await rotateDatabase(database_id);
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
      const confirmed = window.confirm(
        "Deprovision this database? Its data volume is retained."
      );
      if (!confirmed) return;
      await deleteDatabase(database_id);
      if (logsFor === database_id) setLogsFor(null);
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to deprovision database");
    } finally {
      setBusyId(null);
    }
  }

  async function handleShowLogs(database_id: string) {
    if (logsFor === database_id) {
      setLogsFor(null);
      setLogs(null);
      return;
    }
    setLogsFor(database_id);
    setLogsLoading(true);
    setError("");
    try {
      setLogs(await getDatabaseLogs(database_id));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load logs");
      setLogs(null);
    } finally {
      setLogsLoading(false);
    }
  }

  const active = databases.filter((d) => d.status !== "deprovisioned");

  return (
    <div className="bg-[#161616] border border-[#2a2a2a] rounded-2xl p-6">
      <div className="flex items-center justify-between mb-1 flex-wrap gap-3">
        <h2 className="font-mono font-bold text-white text-sm uppercase tracking-wider">
          Databases
        </h2>
        <StatusPill
          status={active.length > 0 ? `${active.length} active` : "0 active"}
        />
      </div>
      <p className="text-[11px] text-gray-600 mb-5">
        Standalone databases. Each one is its own project on the cluster — it
        is never removed with an application.
      </p>

      {error && (
        <p className="mb-4 text-xs text-red-400 bg-red-900/20 border border-red-900/40 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {fullUrl && (
        <div className="mb-4 p-3 bg-[#c8f135]/5 border border-[#c8f135]/30 rounded-xl">
          <p className="text-[11px] font-mono text-[#c8f135] mb-1">
            Connection string (shown only once — save it now)
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
          No databases yet. Provision one below — pick an engine, name it, and
          the platform hands you a connection URL ({engines?.external_host}).
        </p>
      ) : (
        <ul className="space-y-3 mb-5">
          {databases.map((db) => (
            <li
              key={db.database_id}
              className="border border-[#2a2a2a] rounded-xl p-3 flex flex-col gap-3"
            >
              <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      className={`font-mono text-xs font-bold border px-2 py-0.5 rounded-md ${ENGINE_COLORS[db.engine]}`}
                    >
                      {db.engine}
                    </span>
                    <span className="font-mono text-sm text-white font-bold">
                      {db.db_name}
                    </span>
                    <StatusPill status={db.status} />
                    <span className="text-xs text-gray-500 font-mono">
                      {db.size_gb}Gi
                    </span>
                  </div>
                  {db.status === "ready" && (
                    <p className="text-[11px] text-gray-500 font-mono mt-1">
                      {db.host}:{db.node_port ?? db.port}
                      {" · "}
                      {db.storage_class}
                    </p>
                  )}
                  {db.status === "ready" && db.connection_url && (
                    <p className="text-[11px] text-gray-600 font-mono mt-1 truncate">
                      {db.connection_url}
                    </p>
                  )}
                  {db.status === "creating" && (
                    <p className="text-[11px] text-gray-500 font-mono mt-1">
                      n/a — still spinning up
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-2 shrink-0 flex-wrap">
                  {db.status === "ready" && (
                    <>
                      <button
                        onClick={() => handleRotate(db.database_id)}
                        disabled={busyId === db.database_id}
                        className="text-[11px] font-mono px-2.5 py-1.5 rounded-lg border border-[#2a2a2a] text-gray-400 hover:text-gray-200 hover:border-[#3a3a3a] transition-colors disabled:opacity-50"
                      >
                        {busyId === db.database_id ? "…" : "Rotate creds"}
                      </button>
                      <button
                        onClick={() => handleShowLogs(db.database_id)}
                        className="text-[11px] font-mono px-2.5 py-1.5 rounded-lg border border-[#2a2a2a] text-gray-400 hover:text-gray-200 hover:border-[#3a3a3a] transition-colors"
                      >
                        {logsFor === db.database_id ? "Hide logs" : "Logs"}
                      </button>
                    </>
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
                  {db.status !== "deprovisioned" && (
                    <button
                      onClick={() => handleDeprovision(db.database_id)}
                      disabled={busyId === db.database_id}
                      className="text-[11px] font-mono px-2.5 py-1.5 rounded-lg border border-red-900/40 text-red-400 hover:bg-red-900/20 transition-colors disabled:opacity-50"
                    >
                      {busyId === db.database_id ? "…" : "Deprovision"}
                    </button>
                  )}
                </div>
              </div>

              {logsFor === db.database_id && (
                <div className="border-t border-[#2a2a2a] pt-3">
                  {logsLoading ? (
                    <p className="text-[11px] text-gray-500 font-mono animate-pulse">
                      Fetching pod logs…
                    </p>
                  ) : logs && logs.logs.length > 0 ? (
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                      {logs.logs.map((pod) =>
                        pod.containers.map((c) => (
                          <pre
                            key={`${pod.pod_name}-${c.container}`}
                            className="text-[11px] font-mono text-gray-400 whitespace-pre-wrap break-words bg-[#0f0f0f] border border-[#222222] rounded-lg p-3"
                          >
                            [{pod.pod_name}/{c.container}]
                            {"\n"}
                            {c.error
                              ? `error: ${c.error}`
                              : c.logs ?? "(no output)"}
                          </pre>
                        ))
                      )}
                    </div>
                  ) : (
                    <p className="text-[11px] text-gray-500 font-mono">
                      No logs yet — the pod may still be starting.
                    </p>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      <div className="border-t border-[#2a2a2a] pt-5 space-y-4">
        <div className="flex gap-2 flex-wrap">
          {DATABASE_ENGINES.map((entry) => (
            <button
              key={entry.value}
              onClick={() => onEngineChange(entry.value)}
              disabled={provisioning}
              className={`text-xs font-mono px-3 py-2 rounded-xl border transition-colors disabled:opacity-50 ${
                engine === entry.value
                  ? "border-[#c8f135] text-[#c8f135] bg-[#c8f135]/10"
                  : "border-[#2a2a2a] text-gray-400 hover:border-[#3a3a3a]"
              }`}
            >
              {entry.label}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <Field label="Database name *">
            <input
              className={inputClass}
              value={dbName}
              onChange={(e) => setDbName(e.target.value)}
              placeholder="e.g. analytics"
            />
          </Field>
          <Field label="Size (GiB)">
            <select
              className={inputClass}
              value={sizeGb}
              onChange={(e) =>
                setSizeGb(e.target.value === "" ? "" : Number(e.target.value))
              }
            >
              {(engines?.allowed_sizes_gb ?? [1, 5]).map((size) => (
                <option key={size} value={size}>
                  {size} GiB
                </option>
              ))}
            </select>
          </Field>
          <Field label="Host">
            <input
              className={inputClass}
              value={host}
              onChange={(e) => setHost(e.target.value)}
              placeholder={engines?.external_host ?? "cluster host"}
            />
          </Field>
          <Field label="Port">
            <input
              className={inputClass}
              value={port}
              onChange={(e) =>
                setPort(e.target.value === "" ? "" : Number(e.target.value))
              }
              placeholder={String(engines?.engines[engine]?.default_port ?? "")}
            />
          </Field>
          <Field label="Storage class">
            <input
              className={inputClass}
              value={storageClass}
              onChange={(e) => setStorageClass(e.target.value)}
              placeholder={engines?.default_storage_class ?? "local-path"}
            />
          </Field>
          <Field label="Username (optional)">
            <input
              className={inputClass}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="auto-generated"
            />
          </Field>
          <Field label="Password (optional)">
            <input
              className={inputClass}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="auto-generated"
            />
          </Field>
          <label className="flex items-center gap-2 mt-4 cursor-pointer">
            <input
              type="checkbox"
              checked={external}
              onChange={(e) => setExternal(e.target.checked)}
              className="accent-[#c8f135]"
            />
            <span className="text-[11px] font-mono text-gray-500">
              Expose on NodePort (external access)
            </span>
          </label>
        </div>

        <button
          onClick={handleProvision}
          disabled={provisioning}
          className="w-full sm:w-auto font-mono font-bold text-sm px-6 py-2.5 rounded-xl bg-[#c8f135] hover:bg-[#d8f35a] text-black transition-colors disabled:opacity-50"
        >
          {provisioning ? "Provisioning…" : "＋ Provision Database"}
        </button>
        <p className="text-[11px] text-gray-600">
          Your host/port/storage choices are applied literally to the workload
          and the returned connection string. Idempotent: re-provisioning the
          same name rotates credentials instead of duplicating.
        </p>
      </div>
    </div>
  );
}