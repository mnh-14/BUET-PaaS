"use client";

import { Deployment } from "@/lib/api";
import StatusBadge from "./StatusBadge";

interface DeploymentHistoryProps {
  deployments: Deployment[];
}

export default function DeploymentHistory({
  deployments,
}: DeploymentHistoryProps) {
  if (!deployments || deployments.length === 0) {
    return (
      <p className="text-sm text-gray-500 py-4">No deployments yet.</p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-[#2a2a2a]">
            <th className="text-left py-2.5 px-3 text-xs font-mono text-gray-500 uppercase tracking-wider">
              Deployment ID
            </th>
            <th className="text-left py-2.5 px-3 text-xs font-mono text-gray-500 uppercase tracking-wider">
              Status
            </th>
            <th className="text-left py-2.5 px-3 text-xs font-mono text-gray-500 uppercase tracking-wider">
              Port
            </th>
            <th className="text-left py-2.5 px-3 text-xs font-mono text-gray-500 uppercase tracking-wider">
              Deployed At
            </th>
            <th className="text-left py-2.5 px-3 text-xs font-mono text-gray-500 uppercase tracking-wider">
              Error
            </th>
          </tr>
        </thead>
        <tbody>
          {deployments.map((d, idx) => (
            <tr
              key={d.deployment_id}
              className={`border-b border-[#2a2a2a]/60 hover:bg-[#1a1a1a] transition-colors ${
                idx === 0 ? "bg-[#1a1a1a]/30" : ""
              }`}
            >
              <td className="py-2.5 px-3 font-mono text-xs text-gray-400 max-w-[160px]">
                <span className="truncate block" title={d.deployment_id}>
                  {d.deployment_id.slice(0, 8)}…
                </span>
              </td>
              <td className="py-2.5 px-3">
                <StatusBadge status={d.status} />
              </td>
              <td className="py-2.5 px-3 font-mono text-xs text-gray-400">
                {d.port ?? "—"}
              </td>
              <td className="py-2.5 px-3 text-xs text-gray-400">
                {new Date(d.deployed_at).toLocaleString()}
              </td>
              <td className="py-2.5 px-3 text-xs text-red-400 max-w-[200px]">
                {d.error_summary ? (
                  <span className="truncate block" title={d.error_summary}>
                    {d.error_summary}
                  </span>
                ) : (
                  <span className="text-gray-600">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
