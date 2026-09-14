"use client";

import { useEffect, useRef, useState } from "react";
import { DeploymentLogChunk, subscribeToDeploymentLogs } from "@/lib/api";

interface LogLine {
  id: number;
  source: "build" | "deploy";
  text: string;
}

const SOURCE_LABEL: Record<LogLine["source"], string> = {
  build: "build",
  deploy: "deploy",
};

const SOURCE_COLOR: Record<LogLine["source"], string> = {
  build: "text-blue-400",
  deploy: "text-[#c8f135]",
};

export default function DeploymentLogsPanel({ deploymentId }: { deploymentId: string }) {
  const [lines, setLines] = useState<LogLine[]>([]);
  const [connected, setConnected] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const autoScrollRef = useRef(true);
  const nextId = useRef(0);
  const partial = useRef<Record<string, string>>({});

  useEffect(() => {
    setLines([]);
    partial.current = {};
    nextId.current = 0;
    setConnected(true);

    const source = subscribeToDeploymentLogs(
      deploymentId,
      (chunk: DeploymentLogChunk) => {
        const key = `${chunk.source}:${chunk.pod}:${chunk.container}`;
        const combined = (partial.current[key] ?? "") + chunk.text;
        const segments = combined.split("\n");
        partial.current[key] = segments.pop() ?? "";

        if (segments.length === 0) return;
        setLines((current) => [
          ...current,
          ...segments
            .filter((segment) => segment.length > 0)
            .map((segment) => ({
              id: nextId.current++,
              source: chunk.source,
              text: segment,
            })),
        ]);
      },
      () => setConnected(false),
    );

    return () => {
      source.close();
      setConnected(false);
    };
  }, [deploymentId]);

  useEffect(() => {
    if (!autoScrollRef.current || !scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [lines]);

  function handleScroll() {
    const el = scrollRef.current;
    if (!el) return;
    autoScrollRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 32;
  }

  if (lines.length === 0 && !connected) return null;

  return (
    <div className="mt-4">
      <div className="flex items-center gap-2 mb-2">
        <span
          className={`w-2 h-2 rounded-full ${
            connected ? "bg-[#c8f135] animate-pulse" : "bg-gray-600"
          }`}
        />
        <span className="font-mono text-xs uppercase tracking-wider text-gray-400">
          Deployment Logs
        </span>
      </div>
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="bg-black/60 border border-[#2a2a2a] rounded-xl p-3 h-64 overflow-y-auto font-mono text-xs leading-relaxed"
      >
        {lines.length === 0 ? (
          <p className="text-gray-600">Waiting for logs…</p>
        ) : (
          lines.map((line) => (
            <div key={line.id} className="whitespace-pre-wrap break-all text-gray-300">
              <span className={`${SOURCE_COLOR[line.source]} mr-2`}>
                [{SOURCE_LABEL[line.source]}]
              </span>
              {line.text}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
