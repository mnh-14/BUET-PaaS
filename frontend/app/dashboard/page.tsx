"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import Navbar from "@/components/Navbar";
import ProjectCard from "@/components/ProjectCard";
import { getUserProjects, Project } from "@/lib/api";

function SkeletonCard() {
  return (
    <div className="bg-[#161616] border border-[#2a2a2a] rounded-xl p-5 flex flex-col gap-3 animate-pulse">
      <div className="flex justify-between items-center">
        <div className="h-4 bg-[#2a2a2a] rounded w-1/2" />
        <div className="h-5 bg-[#2a2a2a] rounded-full w-16" />
      </div>
      <div className="h-3 bg-[#2a2a2a] rounded w-3/4" />
      <div className="mt-auto pt-2 border-t border-[#2a2a2a] flex justify-between items-center">
        <div className="h-3 bg-[#2a2a2a] rounded w-20" />
        <div className="h-6 bg-[#2a2a2a] rounded w-14" />
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (authLoading) return;
    if (!user) return void router.replace("/");
    getUserProjects(user.user_id)
      .then(setProjects)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Failed to load projects")
      )
      .finally(() => setLoading(false));
  }, [user, authLoading, router]);

  if (authLoading || !user) return null;

  return (
    <div className="min-h-screen bg-[#0d0d0d]">
      <Navbar />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
          <div>
            <h1 className="font-mono font-bold text-2xl text-white">
              Welcome, {user.name}
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              {projects.length} project{projects.length !== 1 ? "s" : ""}
            </p>
          </div>
          <Link
            href="/projects/new"
            className="inline-flex items-center gap-2 bg-[#c8f135] text-black font-mono font-bold px-5 py-2.5 rounded-xl hover:bg-[#d4f84d] transition-colors text-sm shrink-0"
          >
            <span className="text-lg leading-none">+</span>
            New Project
          </Link>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 p-4 bg-red-900/20 border border-red-900/40 rounded-xl text-sm text-red-400">
            {error}
          </div>
        )}

        {/* Grid */}
        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        ) : projects.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 gap-4 text-center">
            <div className="w-16 h-16 rounded-2xl bg-[#161616] border border-[#2a2a2a] flex items-center justify-center text-3xl">
              🚀
            </div>
            <h2 className="font-mono font-bold text-white text-lg">
              No projects yet
            </h2>
            <p className="text-sm text-gray-500 max-w-xs">
              Deploy your first GitHub repo and see it go live in minutes.
            </p>
            <Link
              href="/projects/new"
              className="mt-2 bg-[#c8f135] text-black font-mono font-bold px-6 py-2.5 rounded-xl hover:bg-[#d4f84d] transition-colors text-sm"
            >
              + Create First Project
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map((p) => (
              <ProjectCard key={p.project_id} project={p} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
