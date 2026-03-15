"use client";

import Link from "next/link";
import { Project } from "@/lib/api";
import StatusBadge from "./StatusBadge";

interface ProjectCardProps {
  project: Project;
}

export default function ProjectCard({ project }: ProjectCardProps) {
  const latest = project.deployments?.[0];
  const status = latest?.status ?? "stopped";
  const truncatedUrl =
    project.repo_url.replace("https://github.com/", "").length > 36
      ? project.repo_url.replace("https://github.com/", "").slice(0, 36) + "…"
      : project.repo_url.replace("https://github.com/", "");

  return (
    <div className="bg-[#161616] border border-[#2a2a2a] rounded-xl p-5 flex flex-col gap-3 hover:border-[#3a3a3a] transition-colors">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-mono font-bold text-white text-sm truncate">
          {project.project_name}
        </h3>
        <StatusBadge status={status} />
      </div>

      {/* Repo URL */}
      <a
        href={project.repo_url}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-200 transition-colors truncate group"
        onClick={(e) => e.stopPropagation()}
      >
        <svg
          className="w-3.5 h-3.5 shrink-0 text-gray-600 group-hover:text-gray-400"
          fill="currentColor"
          viewBox="0 0 24 24"
        >
          <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
        </svg>
        <span className="truncate">{truncatedUrl}</span>
        <svg
          className="w-3 h-3 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
          />
        </svg>
      </a>

      {/* Live URL */}
      {status === "running" && latest?.public_url && (
        <a
          href={latest.public_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 text-xs text-[#c8f135] hover:underline truncate"
          onClick={(e) => e.stopPropagation()}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-[#c8f135] animate-pulse shrink-0" />
          {latest.public_url}
        </a>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between mt-auto pt-2 border-t border-[#2a2a2a]">
        <span className="text-xs text-gray-600">
          {new Date(project.created_at).toLocaleDateString()}
        </span>
        <Link
          href={`/projects/${project.project_id}`}
          className="text-xs font-mono font-medium text-[#c8f135] hover:bg-[#c8f135]/10 px-3 py-1 rounded-lg transition-colors border border-[#c8f135]/20 hover:border-[#c8f135]/40"
        >
          View →
        </Link>
      </div>
    </div>
  );
}
