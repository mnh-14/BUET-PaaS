"use client";

import { Deployment, SecurityScanCondition } from "@/lib/api";

const METRIC_LABELS: Record<string, string> = {
  new_security_rating: "Security rating on new code",
  security_rating: "Overall security rating",
  new_vulnerabilities: "New vulnerabilities",
  vulnerabilities: "Vulnerabilities",
  new_security_hotspots_reviewed: "New security hotspots reviewed",
  security_hotspots_reviewed: "Security hotspots reviewed",
};

function conditionText(condition: SecurityScanCondition): string {
  const label = METRIC_LABELS[condition.metric] ?? condition.metric.replaceAll("_", " ");
  const values = [
    condition.actual_value != null ? `actual ${condition.actual_value}` : null,
    condition.error_threshold != null
      ? `required threshold ${condition.error_threshold}`
      : null,
  ].filter(Boolean);
  return `${label}${values.length ? ` — ${values.join(", ")}` : ""}`;
}

export default function SecurityScanPanel({ deployment }: { deployment: Deployment }) {
  const scan = deployment.security_scan;
  const failure = deployment.failure;
  const securityFailure =
    deployment.status === "security_scan_failed" || scan?.status === "failed";
  const scanError =
    deployment.status === "security_scan_error" || scan?.status === "error";

  if (!scan && !securityFailure && !scanError) return null;

  const failedConditions = scan?.conditions?.filter((condition) => condition.status !== "OK") ?? [];
  const issues = scan?.issues ?? [];

  if (scan?.status === "running") {
    return (
      <div className="mt-6 p-4 bg-violet-900/20 border border-violet-800/40 rounded-xl text-sm text-violet-300">
        SonarQube is analyzing commit {scan.commit_sha?.slice(0, 12) ?? "…"}.
      </div>
    );
  }

  if (scan?.status === "passed") {
    return (
      <div className="mt-6 p-4 bg-green-900/20 border border-green-800/40 rounded-xl text-sm text-green-300">
        SonarQube Quality Gate passed for commit {scan.commit_sha?.slice(0, 12)}.
      </div>
    );
  }

  if (!securityFailure && !scanError) return null;

  return (
    <div className="mt-6 p-4 bg-red-900/20 border border-red-800/50 rounded-xl space-y-4">
      <div>
        <h3 className="font-mono font-bold text-red-300 text-sm">
          {failure?.title ?? (securityFailure ? "Deployment blocked by security scan" : "Security scan could not complete")}
        </h3>
        <p className="text-xs text-red-200/80 mt-1">
          {failure?.summary ?? scan?.error ?? deployment.error_summary ?? "SonarQube did not return a usable analysis result."}
        </p>
      </div>

      {failure?.reason && failure.reason !== failure.summary && (
        <div className="bg-black/20 rounded-lg px-3 py-2.5">
          <h4 className="text-[10px] font-mono uppercase tracking-wider text-gray-500 mb-1">Why it failed</h4>
          <p className="text-xs text-gray-200">{failure.reason}</p>
        </div>
      )}

      {failedConditions.length > 0 && (
        <div>
          <h4 className="text-xs font-mono font-bold text-gray-300 mb-2">Why the Quality Gate failed</h4>
          <ul className="space-y-1.5">
            {failedConditions.map((condition, index) => (
              <li key={`${condition.metric}-${index}`} className="text-xs text-red-200 bg-black/20 rounded px-3 py-2">
                {conditionText(condition)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {issues.length > 0 && (
        <div>
          <h4 className="text-xs font-mono font-bold text-gray-300 mb-2">
            Issues to fix {issues.length === 20 ? "(first 20)" : ""}
          </h4>
          <div className="space-y-2">
            {issues.map((issue, index) => (
              <div key={issue.key ?? index} className="bg-black/25 border border-red-900/30 rounded-lg p-3">
                <div className="flex flex-wrap gap-2 text-[10px] font-mono uppercase mb-1.5">
                  {issue.severity && <span className="text-red-300">{issue.severity}</span>}
                  {issue.type && <span className="text-amber-300">{issue.type}</span>}
                  {issue.rule && <span className="text-gray-500">{issue.rule}</span>}
                </div>
                <p className="text-xs text-gray-200">{issue.message}</p>
                {(issue.file || issue.line) && (
                  <p className="mt-1.5 text-xs font-mono text-[#c8f135] break-all">
                    {issue.file ?? "Unknown file"}{issue.line ? `:${issue.line}` : ""}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="text-xs text-gray-400 border-t border-red-900/30 pt-3">
        <p>
          {failure?.suggestion ?? "Fix the reported code, push a new commit, and redeploy. Do not weaken the Quality Gate unless the security policy itself is intentionally changing."}
        </p>
        {scan?.analysis_url && (
          <a
            href={scan.analysis_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex mt-2 text-[#c8f135] hover:underline"
          >
            Open full SonarQube analysis →
          </a>
        )}
      </div>
    </div>
  );
}
