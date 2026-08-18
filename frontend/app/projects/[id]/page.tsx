"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import Navbar from "@/components/Navbar";
import StatusBadge from "@/components/StatusBadge";
import DeploymentHistory from "@/components/DeploymentHistory";
import SecurityScanPanel from "@/components/SecurityScanPanel";
import {
  getProject,
  getDeployment,
  checkProjectUpdate,
  subscribeToDeployment,
  deleteProject,
  redeployProject,
  Project,
  Deployment,
  DeploymentStatus,
  UpdateCheck,
} from "@/lib/api";

// ─── Pipeline ─────────────────────────────────────────────────────────────────

const STAGES: DeploymentStatus[] = [
  "queued",
  "cloning",
  "security_scan_running",
  "building",
  "deploying",
  "running",
];

const STAGE_LABELS: Record<string, string> = {
  queued: "Queued",
  cloning: "Cloning",
  security_scan_running: "Security Scan",
  building: "Building",
  deploying: "Deploying",
  running: "Running",
};

const ACTIVE_STATUSES: DeploymentStatus[] = [
  "queued",
  "cloning",
  "security_scan_running",
  "security_scan_passed",
  "submitting_build",
  "building",
  "deploying",
  "waiting_for_pods",
];

function Pipeline({ status }: { status: DeploymentStatus }) {
  const normalizedStatus =
    status === "security_scan_passed" || status === "submitting_build"
      ? "building"
      : status === "waiting_for_pods"
        ? "deploying"
        : status;
  const currentIdx = STAGES.indexOf(normalizedStatus);
  const securityFailed =
    status === "security_scan_failed" || status === "security_scan_error";
  const failed = status === "failed" || securityFailed;
  const failedIdx = securityFailed
    ? STAGES.indexOf("security_scan_running")
    : Math.max(currentIdx, 0);

  return (
    <div className="flex items-center gap-0 overflow-x-auto py-2">
      {STAGES.map((stage, idx) => {
        const isDone = idx < (failed ? failedIdx : currentIdx);
        const isCurrent = !failed && currentIdx === idx;
        const isFailed = failed && idx === failedIdx;

        return (
          <div key={stage} className="flex items-center">
            {/* Node */}
            <div className="flex flex-col items-center gap-1.5 min-w-[72px]">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-all ${
                  isFailed
                    ? "bg-red-900/40 border-red-600 text-red-400"
                    : isDone
                    ? "bg-green-900/40 border-green-500 text-green-400"
                    : isCurrent && !failed
                    ? "bg-[#c8f135]/10 border-[#c8f135] text-[#c8f135] animate-pulse"
                    : "bg-[#1a1a1a] border-[#2a2a2a] text-gray-600"
                }`}
              >
                {isDone ? "✓" : isFailed ? "✗" : idx + 1}
              </div>
              <span
                className={`text-[10px] font-mono whitespace-nowrap ${
                  isFailed
                    ? "text-red-400"
                    : isDone
                    ? "text-green-400"
                    : isCurrent && !failed
                    ? "text-[#c8f135]"
                    : "text-gray-600"
                }`}
              >
                {STAGE_LABELS[stage]}
              </span>
            </div>

            {/* Connector */}
            {idx < STAGES.length - 1 && (
              <div
                className={`h-0.5 w-8 sm:w-12 mb-5 shrink-0 transition-all ${
                  (failed ? failedIdx : currentIdx) > idx
                    ? "bg-green-500/60"
                    : "bg-[#2a2a2a]"
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Delete Modal ─────────────────────────────────────────────────────────────

function DeleteModal({
  projectName,
  onConfirm,
  onCancel,
  loading,
}: {
  projectName: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading: boolean;
}) {
  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-[#161616] border border-[#2a2a2a] rounded-2xl p-6 max-w-sm w-full">
        <h3 className="font-mono font-bold text-white text-lg mb-2">
          Delete Project?
        </h3>
        <p className="text-sm text-gray-400 mb-6">
          This will permanently delete{" "}
          <span className="text-white font-mono">{projectName}</span> and all
          its deployments. This action cannot be undone.
        </p>
        <div className="flex gap-3">
          <button
            onClick={onConfirm}
            disabled={loading}
            className="flex-1 bg-red-600 hover:bg-red-500 text-white font-mono font-bold py-2.5 rounded-xl transition-colors disabled:opacity-50"
          >
            {loading ? "Deleting…" : "Yes, Delete"}
          </button>
          <button
            onClick={onCancel}
            className="flex-1 border border-[#2a2a2a] text-gray-400 hover:text-gray-200 hover:border-[#3a3a3a] py-2.5 rounded-xl transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ProjectDetailPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const params = useParams();
  const projectId = params.id as string;

  const [project, setProject] = useState<Project | null>(null);
  const [latestDeployment, setLatestDeployment] = useState<Deployment | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [redeployLoading, setRedeployLoading] = useState(false);
  const [actionError, setActionError] = useState("");
  const [updateCheck, setUpdateCheck] = useState<UpdateCheck | null>(null);
  const [checkingUpdate, setCheckingUpdate] = useState(false);

  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!authLoading && !user) router.replace("/");
  }, [user, authLoading, router]);

  const stopEvents = useCallback(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
  }, []);

  const startEvents = useCallback(
    (deploymentId: string) => {
      stopEvents();
      eventSourceRef.current = subscribeToDeployment(
        deploymentId,
        (deployment) => {
          setLatestDeployment(deployment);
          if (!ACTIVE_STATUSES.includes(deployment.status)) {
            stopEvents();
            getProject(projectId).then(setProject).catch(() => {});
          }
        },
        () => {
          getDeployment(deploymentId).then(setLatestDeployment).catch(() => {});
        },
      );
    },
    [stopEvents, projectId]
  );

  // Initial load
  useEffect(() => {
    if (!user) return;

    getProject(projectId)
      .then((p) => {
        setProject(p);
        const latest = p.deployments?.[0] ?? null;
        setLatestDeployment(latest);

        if (latest && ACTIVE_STATUSES.includes(latest.status)) {
          startEvents(latest.deployment_id);
        }
        setCheckingUpdate(true);
        checkProjectUpdate(projectId)
          .then(setUpdateCheck)
          .catch((err: unknown) =>
            setActionError(err instanceof Error ? err.message : "Could not check GitHub")
          )
          .finally(() => setCheckingUpdate(false));
      })
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Failed to load project")
      )
      .finally(() => setLoading(false));

    return () => stopEvents();
  }, [user, projectId, startEvents, stopEvents]);

  async function handleCheckUpdate() {
    setCheckingUpdate(true);
    setActionError("");
    try {
      setUpdateCheck(await checkProjectUpdate(projectId));
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Could not check GitHub");
    } finally {
      setCheckingUpdate(false);
    }
  }

  async function handleDelete() {
    setDeleteLoading(true);
    try {
      await deleteProject(projectId);
      router.push("/dashboard");
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to delete");
      setDeleteLoading(false);
      setShowDeleteModal(false);
    }
  }

  async function handleRedeploy() {
    setActionError("");
    setRedeployLoading(true);
    try {
      const data = await redeployProject(projectId);
      const newDeploy: Deployment = {
        deployment_id: data.deployment_id,
        project_id: projectId,
        status: "queued",
        deployed_at: new Date().toISOString(),
      };
      setLatestDeployment(newDeploy);
      setUpdateCheck((current) => current ? { ...current, latest_remote_sha: data.commit_sha } : current);
      startEvents(data.deployment_id);
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to redeploy");
    } finally {
      setRedeployLoading(false);
    }
  }

  if (authLoading || !user) return null;
  const deploymentActive = latestDeployment
    ? ACTIVE_STATUSES.includes(latestDeployment.status)
    : false;
  const canDeploy = Boolean(updateCheck?.update_available) && !deploymentActive;

  return (
    <div className="min-h-screen bg-[#0d0d0d]">
      <Navbar />

      {showDeleteModal && project && (
        <DeleteModal
          projectName={project.project_name}
          onConfirm={handleDelete}
          onCancel={() => setShowDeleteModal(false)}
          loading={deleteLoading}
        />
      )}

      <main className="max-w-4xl mx-auto px-4 sm:px-6 py-10">
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-300 transition-colors mb-6"
        >
          ← Back to Dashboard
        </Link>

        {loading && (
          <div className="space-y-4 animate-pulse">
            <div className="h-8 bg-[#2a2a2a] rounded w-1/3" />
            <div className="h-4 bg-[#2a2a2a] rounded w-1/2" />
            <div className="h-48 bg-[#161616] border border-[#2a2a2a] rounded-2xl mt-6" />
          </div>
        )}

        {error && !loading && (
          <div className="p-4 bg-red-900/20 border border-red-900/40 rounded-xl text-sm text-red-400">
            {error}
          </div>
        )}

        {project && !loading && (
          <div className="space-y-6">
            {/* Header */}
            <div className="bg-[#161616] border border-[#2a2a2a] rounded-2xl p-6">
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 flex-wrap">
                    <h1 className="font-mono font-bold text-2xl text-white">
                      {project.project_name}
                    </h1>
                    {latestDeployment && (
                      <StatusBadge status={latestDeployment.status} />
                    )}
                  </div>
                  <a
                    href={project.repo_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-200 transition-colors"
                  >
                    <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
                    </svg>
                    {project.repo_url}
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </a>
                  <p className="text-xs text-gray-600 mt-1">
                    Created {new Date(project.created_at).toLocaleDateString()}
                  </p>
                  <div className="mt-3 text-xs font-mono text-gray-500 space-y-1">
                    <p>Branch: <span className="text-gray-300">{project.deploy_branch}</span></p>
                    <p>Deployed: <span className="text-gray-300">{updateCheck?.last_deployed_sha?.slice(0, 8) ?? "Never"}</span></p>
                    <p>Latest: <span className="text-gray-300">{updateCheck?.latest_remote_sha?.slice(0, 8) ?? "Checking…"}</span></p>
                  </div>
                </div>

                {/* Action buttons */}
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={handleRedeploy}
                    disabled={redeployLoading || checkingUpdate || !canDeploy}
                    className="text-sm font-mono px-4 py-2 rounded-xl border border-[#c8f135]/30 text-[#c8f135] hover:bg-[#c8f135]/10 transition-colors disabled:opacity-50"
                  >
                    {redeployLoading ? "Starting…" : "Deploy latest commit"}
                  </button>
                  <button
                    onClick={handleCheckUpdate}
                    disabled={checkingUpdate || deploymentActive}
                    className="text-sm font-mono px-4 py-2 rounded-xl border border-[#333] text-gray-300 hover:border-[#555] transition-colors disabled:opacity-50"
                  >
                    {checkingUpdate ? "Checking…" : "Check updates"}
                  </button>
                  <button
                    onClick={() => { setActionError(""); setShowDeleteModal(true); }}
                    className="text-sm font-mono px-4 py-2 rounded-xl border border-red-900/40 text-red-400 hover:bg-red-900/20 transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </div>

              {actionError && (
                <p className="mt-3 text-xs text-red-400 bg-red-900/20 border border-red-900/40 rounded-lg px-3 py-2">
                  {actionError}
                </p>
              )}
            </div>

            {/* Live deployment status */}
            {latestDeployment && (
              <div className="bg-[#161616] border border-[#2a2a2a] rounded-2xl p-6">
                <h2 className="font-mono font-bold text-white text-sm mb-5 uppercase tracking-wider">
                  Deployment Status
                </h2>

                <Pipeline status={latestDeployment.status} />

                <SecurityScanPanel deployment={latestDeployment} />

                {/* Running state */}
                {latestDeployment.status === "running" &&
                  latestDeployment.public_url && (
                    <div className="mt-6 p-4 bg-green-900/20 border border-green-800/40 rounded-xl">
                      <div className="flex items-center gap-2 mb-3">
                        <span className="w-2.5 h-2.5 rounded-full bg-green-400 animate-pulse" />
                        <span className="font-mono font-bold text-green-400 text-sm">
                          Live
                        </span>
                      </div>
                      <a
                        href={latestDeployment.public_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-2 bg-green-500 hover:bg-green-400 text-black font-mono font-bold px-5 py-2.5 rounded-xl transition-colors text-sm"
                      >
                        Open App
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                        </svg>
                      </a>
                      <p className="text-xs text-gray-500 mt-2">
                        {latestDeployment.public_url}
                      </p>
                    </div>
                  )}

                {/* Failed state */}
                {latestDeployment.status === "failed" && (
                  <div className="mt-6 p-4 bg-red-900/20 border border-red-800/40 rounded-xl">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-red-400 font-mono font-bold text-sm">
                        Deployment Failed
                      </span>
                    </div>
                    {latestDeployment.error_summary && (
                      <pre className="text-xs text-red-300 bg-red-900/20 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-all">
                        {latestDeployment.error_summary}
                      </pre>
                    )}
                  </div>
                )}

                {/* In-progress state */}
                {ACTIVE_STATUSES.includes(latestDeployment.status) && (
                  <div className="mt-4 flex items-center gap-2 text-xs text-gray-500">
                    <span className="w-3 h-3 border-2 border-gray-600 border-t-[#c8f135] rounded-full animate-spin" />
                    Receiving live deployment updates…
                  </div>
                )}
              </div>
            )}

            {/* Deployment history */}
            <div className="bg-[#161616] border border-[#2a2a2a] rounded-2xl p-6">
              <h2 className="font-mono font-bold text-white text-sm mb-5 uppercase tracking-wider">
                Deployment History
              </h2>
              <DeploymentHistory deployments={project.deployments ?? []} />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
