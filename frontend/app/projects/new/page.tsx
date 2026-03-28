"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import Navbar from "@/components/Navbar";
import { createProject } from "@/lib/api";

interface GitHubRepo {
  id: number;
  name: string;
  full_name: string;
  clone_url: string;
  html_url: string;
  private: boolean;
  updated_at: string;
}

interface EnvVarRow {
  id: string;
  key: string;
  value: string;
}

function makeEnvVarRow(): EnvVarRow {
  return {
    id: `env-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    key: "",
    value: "",
  };
}

export default function NewProjectPage() {
  const { user } = useAuth();
  const router = useRouter();

  const [repoUrl, setRepoUrl] = useState("");
  const [projectName, setProjectName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // GitHub repo browser state
  const [githubUsername, setGithubUsername] = useState("");
  const [repos, setRepos] = useState<GitHubRepo[]>([]);
  const [repoLoading, setRepoLoading] = useState(false);
  const [repoError, setRepoError] = useState("");
  const [showRepoDropdown, setShowRepoDropdown] = useState(false);
  const [repoFilter, setRepoFilter] = useState("");
  const [envVars, setEnvVars] = useState<EnvVarRow[]>([makeEnvVarRow()]);

  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!user) router.replace("/");
  }, [user, router]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setShowRepoDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  async function handleFetchRepos(e: React.FormEvent) {
    e.preventDefault();
    if (!githubUsername.trim()) return;
    setRepoLoading(true);
    setRepoError("");
    setRepos([]);
    setShowRepoDropdown(false);
    try {
      const res = await fetch(
        `https://api.github.com/users/${githubUsername.trim()}/repos?sort=updated&per_page=100`,
      );
      if (!res.ok) {
        if (res.status === 404)
          throw new Error(`GitHub user "${githubUsername}" not found`);
        throw new Error(`GitHub API error: ${res.status}`);
      }
      const list: GitHubRepo[] = await res.json();
      const publicRepos = list.filter((r) => !r.private);
      if (publicRepos.length === 0) {
        setRepoError("No public repositories found for this user");
      } else {
        setRepos(publicRepos);
        setShowRepoDropdown(true);
      }
    } catch (err: unknown) {
      setRepoError(
        err instanceof Error ? err.message : "Failed to fetch repos",
      );
    } finally {
      setRepoLoading(false);
    }
  }

  function selectRepo(repo: GitHubRepo) {
    setRepoUrl(repo.clone_url);
    setProjectName(repo.name);
    setShowRepoDropdown(false);
    setRepoFilter("");
  }

  function addEnvVarRow() {
    setEnvVars((prev) => [...prev, makeEnvVarRow()]);
  }

  function removeEnvVarRow(id: string) {
    setEnvVars((prev) => prev.filter((row) => row.id !== id));
  }

  function updateEnvVarRow(
    id: string,
    field: "key" | "value",
    value: string,
  ) {
    setEnvVars((prev) =>
      prev.map((row) => (row.id === id ? { ...row, [field]: value } : row)),
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!user) return;
    setError("");
    setLoading(true);

    const envMap: Record<string, string> = {};
    for (const row of envVars) {
      const key = row.key.trim();
      const value = row.value.trim();

      if (!key) continue;
      if (Object.hasOwn(envMap, key)) {
        setError(`Duplicate environment variable key: ${key}`);
        setLoading(false);
        return;
      }
      envMap[key] = value;
    }

    try {
      const data = await createProject({
        repo_url: repoUrl,
        user_id: user.user_id,
        project_name: projectName,
        env_vars: envMap,
      });
      router.push(`/projects/${data.project_id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create project");
    } finally {
      setLoading(false);
    }
  }

  const filteredRepos = repos.filter((r) =>
    r.name.toLowerCase().includes(repoFilter.toLowerCase()),
  );

  const inputClass =
    "w-full bg-[#0d0d0d] border border-[#2a2a2a] rounded-lg px-4 py-2.5 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-[#c8f135]/60 focus:ring-1 focus:ring-[#c8f135]/20 transition-colors";

  if (!user) return null;

  return (
    <div className="min-h-screen bg-[#0d0d0d]">
      <Navbar />

      <main className="max-w-2xl mx-auto px-4 sm:px-6 py-10">
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-300 transition-colors mb-6"
        >
          ← Back to Dashboard
        </Link>

        <div className="bg-[#161616] border border-[#2a2a2a] rounded-2xl p-8">
          <h1 className="font-mono font-bold text-xl text-white mb-1">
            New Project
          </h1>
          <p className="text-sm text-gray-500 mb-8">
            Deploy a GitHub repository to BUET-PaaS.
          </p>

          {/* GitHub username browser */}
          <div className="mb-6">
            <label className="block text-xs font-mono text-gray-400 mb-1.5">
              Browse by GitHub Username
            </label>
            <form onSubmit={handleFetchRepos} className="flex gap-2">
              <div className="flex-1 relative">
                <input
                  type="text"
                  className={inputClass}
                  placeholder="e.g. torvalds"
                  value={githubUsername}
                  onChange={(e) => setGithubUsername(e.target.value)}
                />
              </div>
              <button
                type="submit"
                disabled={repoLoading || !githubUsername.trim()}
                className="flex items-center gap-2 px-4 text-xs font-mono text-[#c8f135] hover:bg-[#c8f135]/10 rounded-lg border border-[#c8f135]/20 hover:border-[#c8f135]/40 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
              >
                {repoLoading ? (
                  <>
                    <span className="w-3.5 h-3.5 border-2 border-[#c8f135]/30 border-t-[#c8f135] rounded-full animate-spin" />
                    Loading…
                  </>
                ) : (
                  <>
                    <svg
                      className="w-3.5 h-3.5"
                      fill="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
                    </svg>
                    Fetch Repos
                  </>
                )}
              </button>
            </form>

            {repoError && (
              <p className="mt-1.5 text-xs text-red-400">{repoError}</p>
            )}

            {/* Repos dropdown */}
            <div className="relative" ref={dropdownRef}>
              {showRepoDropdown && repos.length > 0 && (
                <div className="absolute top-1 left-0 w-full bg-[#161616] border border-[#2a2a2a] rounded-xl shadow-2xl z-50 overflow-hidden">
                  <div className="p-2 border-b border-[#2a2a2a]">
                    <input
                      type="text"
                      className="w-full bg-[#0d0d0d] border border-[#2a2a2a] rounded-lg px-3 py-1.5 text-xs text-gray-100 placeholder-gray-600 focus:outline-none focus:border-[#c8f135]/50"
                      placeholder="Filter repos…"
                      value={repoFilter}
                      onChange={(e) => setRepoFilter(e.target.value)}
                      autoFocus
                    />
                  </div>
                  <div className="overflow-y-auto max-h-64">
                    {filteredRepos.length === 0 ? (
                      <p className="text-xs text-gray-500 px-3 py-3">
                        No repos match
                      </p>
                    ) : (
                      filteredRepos.map((repo) => (
                        <button
                          key={repo.id}
                          type="button"
                          onClick={() => selectRepo(repo)}
                          className="w-full text-left px-3 py-2.5 hover:bg-[#1a1a1a] transition-colors border-b border-[#2a2a2a]/50 last:border-0"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-mono text-gray-200 truncate">
                              {repo.name}
                            </span>
                          </div>
                          <p className="text-[10px] text-gray-600 mt-0.5">
                            Updated{" "}
                            {new Date(repo.updated_at).toLocaleDateString()}
                          </p>
                        </button>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-6">
            {/* GitHub Repo URL */}
            <div>
              <label className="block text-xs font-mono text-gray-400 mb-1.5">
                GitHub Repo URL
              </label>
              <input
                type="url"
                className={inputClass}
                placeholder="https://github.com/username/repo"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                required
              />
            </div>

            {/* Project Name */}
            <div>
              <label className="block text-xs font-mono text-gray-400 mb-1.5">
                Project Name
              </label>
              <input
                type="text"
                className={inputClass}
                placeholder="my-project"
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                required
              />
            </div>

            {/* Environment Variables */}
            <div>
              <div className="flex items-center justify-between gap-3 mb-1.5">
                <label className="block text-xs font-mono text-gray-400">
                  Environment Variables (Optional)
                </label>
                <button
                  type="button"
                  onClick={addEnvVarRow}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#c8f135]/20 text-xs font-mono text-[#c8f135] hover:bg-[#c8f135]/10 hover:border-[#c8f135]/40 transition-colors"
                >
                  <span className="text-sm leading-none">+</span>
                  Add Variable
                </button>
              </div>
              <p className="text-xs text-gray-600 mb-3">
                These values are passed to your app container at runtime.
              </p>

              <div className="bg-[#121212] border border-[#2a2a2a] rounded-xl p-3 sm:p-4 space-y-2.5">
                {envVars.length === 0 ? (
                  <p className="text-xs text-gray-600">
                    No variables added yet. Click Add Variable.
                  </p>
                ) : (
                  envVars.map((row) => (
                    <div
                      key={row.id}
                      className="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] gap-2"
                    >
                      <input
                        type="text"
                        className={inputClass}
                        placeholder="KEY"
                        value={row.key}
                        onChange={(e) =>
                          updateEnvVarRow(row.id, "key", e.target.value)
                        }
                      />
                      <input
                        type="text"
                        className={inputClass}
                        placeholder="value"
                        value={row.value}
                        onChange={(e) =>
                          updateEnvVarRow(row.id, "value", e.target.value)
                        }
                      />
                      <button
                        type="button"
                        onClick={() => removeEnvVarRow(row.id)}
                        className="px-3 py-2.5 rounded-lg border border-red-900/40 text-xs font-mono text-red-400 hover:bg-red-900/20 transition-colors"
                      >
                        Remove
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>

            {error && (
              <p className="text-xs text-red-400 bg-red-900/20 border border-red-900/40 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            <div className="flex items-center gap-3 pt-2">
              <button
                type="submit"
                disabled={loading}
                className="flex-1 bg-[#c8f135] text-black font-mono font-bold py-2.5 rounded-xl hover:bg-[#d4f84d] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? "Deploying…" : "🚀 Deploy Project"}
              </button>
              <Link
                href="/dashboard"
                className="px-5 py-2.5 rounded-xl border border-[#2a2a2a] text-sm text-gray-400 hover:border-[#3a3a3a] hover:text-gray-200 transition-colors"
              >
                Cancel
              </Link>
            </div>
          </form>
        </div>
      </main>
    </div>
  );
}
