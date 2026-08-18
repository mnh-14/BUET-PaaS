"use client";

import { DeploymentStatus } from "@/lib/api";

const statusConfig: Record<
  DeploymentStatus,
  { label: string; classes: string }
> = {
  queued: {
    label: "Queued",
    classes: "bg-gray-800 text-gray-300 border border-gray-700",
  },
  cloning: {
    label: "Cloning",
    classes: "bg-blue-900/50 text-blue-300 border border-blue-800",
  },
  security_scan_running: {
    label: "Security Scan",
    classes: "bg-violet-900/50 text-violet-300 border border-violet-800",
  },
  security_scan_passed: {
    label: "Scan Passed",
    classes: "bg-green-900/50 text-green-300 border border-green-800",
  },
  security_scan_failed: {
    label: "Security Failed",
    classes: "bg-red-900/50 text-red-300 border border-red-800",
  },
  security_scan_error: {
    label: "Scan Error",
    classes: "bg-red-900/50 text-red-300 border border-red-800",
  },
  build_queued: {
    label: "Build Queued",
    classes: "bg-amber-900/50 text-amber-300 border border-amber-800",
  },
  build_started: {
    label: "Build Started",
    classes: "bg-amber-900/50 text-amber-300 border border-amber-800",
  },
  build_done: {
    label: "Build Done",
    classes: "bg-green-900/50 text-green-300 border border-green-800",
  },
  deploy_queued: {
    label: "Deploy Queued",
    classes: "bg-orange-900/50 text-orange-300 border border-orange-800",
  },
  deploy_started: {
    label: "Deploy Started",
    classes: "bg-orange-900/50 text-orange-300 border border-orange-800",
  },
  running: {
    label: "Running",
    classes: "bg-green-900/50 text-green-300 border border-green-800",
  },
  failed: {
    label: "Failed",
    classes: "bg-red-900/50 text-red-300 border border-red-800",
  },
  stopped: {
    label: "Stopped",
    classes: "bg-gray-800/80 text-gray-500 border border-gray-700",
  },
};

interface StatusBadgeProps {
  status: DeploymentStatus;
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  const config = statusConfig[status] ?? statusConfig.stopped;
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono font-medium ${config.classes}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${
          status === "running"
            ? "bg-green-400 animate-pulse"
            : status === "failed" ||
              status === "security_scan_failed" ||
              status === "security_scan_error"
            ? "bg-red-400"
            : "bg-current opacity-60"
        }`}
      />
      {config.label}
    </span>
  );
}
