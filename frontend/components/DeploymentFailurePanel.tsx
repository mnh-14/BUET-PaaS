"use client";

import { Deployment } from "@/lib/api";

const SOURCE_LABELS: Record<string, string> = {
  git: "Git",
  sonarqube: "SonarQube",
  kubernetes: "Kubernetes",
  backend: "Backend",
};

function stageLabel(stage?: string): string {
  return stage ? stage.replaceAll("_", " ") : "deployment";
}

export default function DeploymentFailurePanel({ deployment }: { deployment: Deployment }) {
  if (deployment.status !== "failed") return null;

  const failure = deployment.failure;
  const title = failure?.title ?? "Deployment failed";
  const summary = failure?.summary ?? deployment.error_summary;

  return (
    <div className="mt-6 p-4 bg-red-900/20 border border-red-800/50 rounded-xl space-y-4">
      <div>
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <h3 className="font-mono font-bold text-red-300 text-sm">{title}</h3>
          {failure?.source && (
            <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-red-950/60 border border-red-800/50 text-red-300">
              {SOURCE_LABELS[failure.source] ?? failure.source}
            </span>
          )}
          {(failure?.stage || deployment.failed_stage) && (
            <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-black/30 border border-gray-700 text-gray-400">
              {stageLabel(failure?.stage ?? deployment.failed_stage)}
            </span>
          )}
        </div>
        {summary && <p className="text-xs text-red-200/90 break-words">{summary}</p>}
      </div>

      {failure?.reason && failure.reason !== summary && (
        <div className="bg-black/20 rounded-lg px-3 py-2.5">
          <h4 className="text-[10px] font-mono uppercase tracking-wider text-gray-500 mb-1">Why it failed</h4>
          <p className="text-xs text-gray-200 break-words">{failure.reason}</p>
        </div>
      )}

      {failure?.suggestion && (
        <div className="bg-amber-900/10 border border-amber-800/30 rounded-lg px-3 py-2.5">
          <h4 className="text-[10px] font-mono uppercase tracking-wider text-amber-400 mb-1">What to do</h4>
          <p className="text-xs text-amber-100/80">{failure.suggestion}</p>
        </div>
      )}

      {failure?.details && Object.keys(failure.details).length > 0 && (
        <details className="text-xs text-gray-400">
          <summary className="cursor-pointer font-mono hover:text-gray-200">Technical details</summary>
          <pre className="mt-2 bg-black/30 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-words text-[11px]">
            {JSON.stringify(failure.details, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}
