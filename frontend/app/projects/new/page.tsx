"use client";

import { v4 as uuidv4 } from "uuid";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Navbar from "@/components/Navbar";
import { useAuth } from "@/context/AuthContext";
import {
  createProject,
  getGitHubBranches,
  getGitHubInstallations,
  getGitHubRepositories,
  GitHubBranch,
  GitHubInstallation,
  GitHubRepository,
} from "@/lib/api";

interface EnvRow { id: string; key: string; value: string }
const newRow = (): EnvRow => ({ id: uuidv4(), key: "", value: "" });

export default function NewProjectPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [installations, setInstallations] = useState<GitHubInstallation[]>([]);
  const [repositories, setRepositories] = useState<GitHubRepository[]>([]);
  const [branches, setBranches] = useState<GitHubBranch[]>([]);
  const [repositoryId, setRepositoryId] = useState("");
  const [branch, setBranch] = useState("");
  const [projectName, setProjectName] = useState("");
  const [envRows, setEnvRows] = useState<EnvRow[]>([newRow()]);
  const [loading, setLoading] = useState(true);
  const [branchLoading, setBranchLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const selected = useMemo(
    () => repositories.find((repo) => String(repo.id) === repositoryId),
    [repositories, repositoryId],
  );

  useEffect(() => {
    const githubState = new URLSearchParams(window.location.search).get("github");
    if (githubState === "pending") {
      setNotice("GitHub organization-owner approval is pending. Reconnect after an owner approves the installation.");
    } else if (githubState === "connected") {
      setNotice("GitHub access connected successfully.");
    }
  }, []);

  useEffect(() => {
    if (authLoading) return;
    if (!user) return void router.replace("/");
    Promise.all([getGitHubInstallations(), getGitHubRepositories()])
      .then(([connected, repos]) => {
        setInstallations(connected);
        setRepositories(repos);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Could not load GitHub access"))
      .finally(() => setLoading(false));
  }, [user, authLoading, router]);

  useEffect(() => {
    if (!selected) {
      setBranches([]);
      setBranch("");
      return;
    }
    setProjectName(selected.name);
    setBranchLoading(true);
    getGitHubBranches(selected.id, selected.installation_id)
      .then((items) => {
        setBranches(items);
        setBranch(items.some((item) => item.name === selected.default_branch)
          ? selected.default_branch
          : items[0]?.name ?? "");
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Could not load branches"))
      .finally(() => setBranchLoading(false));
  }, [selected]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!selected || !branch) return;
    const env_vars: Record<string, string> = {};
    for (const row of envRows) {
      if (!row.key.trim()) continue;
      if (Object.hasOwn(env_vars, row.key.trim())) {
        return setError(`Duplicate environment variable: ${row.key.trim()}`);
      }
      env_vars[row.key.trim()] = row.value;
    }
    setSubmitting(true);
    setError("");
    try {
      const result = await createProject({
        github_installation_id: selected.installation_id,
        github_repo_id: selected.id,
        deploy_branch: branch,
        project_name: projectName,
        env_vars,
      });
      router.push(`/projects/${result.project_id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Project creation failed");
    } finally {
      setSubmitting(false);
    }
  }

  if (authLoading || !user) return null;
  const active = installations.filter(
    (item) => item.status === "active" && item.connection_status === "active",
  );
  const pendingOrRevoked = installations.filter(
    (item) => item.status !== "active" || item.connection_status !== "active",
  );
  const input = "w-full bg-[#0d0d0d] border border-[#2a2a2a] rounded-lg px-4 py-2.5 text-sm text-gray-100 focus:outline-none focus:border-[#c8f135]/60";

  return (
    <div className="min-h-screen bg-[#0d0d0d]">
      <Navbar />
      <main className="max-w-2xl mx-auto px-4 sm:px-6 py-10">
        <Link href="/dashboard" className="text-sm text-gray-500 hover:text-gray-300">← Back to Dashboard</Link>
        <div className="mt-6 bg-[#161616] border border-[#2a2a2a] rounded-2xl p-8">
          <div className="flex items-start justify-between gap-4 mb-8">
            <div>
              <h1 className="font-mono font-bold text-xl text-white">New Project</h1>
              <p className="text-sm text-gray-500 mt-1">Deploy an authorized public or private repository.</p>
            </div>
            {active.length > 0 && (
              <a href="/api/v1/github/connect" className="text-xs text-[#c8f135] hover:underline">Manage GitHub access</a>
            )}
          </div>

          {error && <p className="mb-5 text-xs text-red-300 bg-red-900/20 border border-red-900/40 rounded-lg p-3">{error}</p>}
          {notice && <p className="mb-5 text-xs text-amber-200 bg-amber-900/20 border border-amber-900/40 rounded-lg p-3">{notice}</p>}

          {!loading && active.length === 0 ? (
            <div className="text-center py-10 border border-dashed border-[#333] rounded-xl">
              <p className="text-sm text-gray-300">No active GitHub App installation</p>
              <p className="text-xs text-gray-500 mt-2">
                Install BUET-PaaS and select the repositories you want to deploy.
              </p>
              {pendingOrRevoked.length > 0 && (
                <p className="text-xs text-amber-300 mt-2">An installation is pending approval, suspended, or revoked.</p>
              )}
              <a href="/api/v1/github/connect" className="inline-flex mt-5 bg-[#c8f135] text-black font-mono font-bold px-5 py-2.5 rounded-lg">
                Connect GitHub
              </a>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-6">
              <div>
                <label className="block text-xs font-mono text-gray-400 mb-1.5">Repository</label>
                <select className={input} value={repositoryId} onChange={(e) => setRepositoryId(e.target.value)} required disabled={loading}>
                  <option value="">{loading ? "Loading repositories…" : repositories.length ? "Select repository" : "No accessible repositories"}</option>
                  {repositories.map((repo) => (
                    <option key={`${repo.installation_id}-${repo.id}`} value={repo.id}>
                      {repo.full_name} · {repo.private ? "Private" : "Public"} · {repo.account_login}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-mono text-gray-400 mb-1.5">Deployment branch</label>
                <select className={input} value={branch} onChange={(e) => setBranch(e.target.value)} required disabled={!selected || branchLoading}>
                  <option value="">{branchLoading ? "Loading branches…" : "Select branch"}</option>
                  {branches.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}
                </select>
              </div>

              <div>
                <label className="block text-xs font-mono text-gray-400 mb-1.5">Project name</label>
                <input className={input} value={projectName} onChange={(e) => setProjectName(e.target.value)} required />
              </div>

              <div>
                <div className="flex justify-between items-center mb-2">
                  <label className="text-xs font-mono text-gray-400">Environment variables</label>
                  <button type="button" onClick={() => setEnvRows((rows) => [...rows, newRow()])} className="text-xs text-[#c8f135]">+ Add variable</button>
                </div>
                <div className="space-y-2">
                  {envRows.map((row) => (
                    <div key={row.id} className="grid grid-cols-[1fr_1fr_auto] gap-2">
                      <input className={input} placeholder="KEY" value={row.key} onChange={(e) => setEnvRows((rows) => rows.map((item) => item.id === row.id ? {...item, key: e.target.value} : item))} />
                      <input className={input} placeholder="value" value={row.value} onChange={(e) => setEnvRows((rows) => rows.map((item) => item.id === row.id ? {...item, value: e.target.value} : item))} />
                      <button type="button" onClick={() => setEnvRows((rows) => rows.filter((item) => item.id !== row.id))} className="text-red-400 px-2">×</button>
                    </div>
                  ))}
                </div>
              </div>

              <button type="submit" disabled={!selected || !branch || submitting} className="w-full bg-[#c8f135] text-black font-mono font-bold py-2.5 rounded-lg disabled:opacity-50">
                {submitting ? "Queuing exact commit…" : "Deploy Project →"}
              </button>
            </form>
          )}
        </div>
      </main>
    </div>
  );
}
