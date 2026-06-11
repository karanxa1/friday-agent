"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { PageShell } from "@/components/AppNav";
import { getJSON } from "@/lib/api";

export default function MemoryPage() {
  const [memory, setMemory] = useState<string>("");
  const [error, setError] = useState(false);

  useEffect(() => {
    getJSON<{ memory: string }>("/api/memory")
      .then((r) => setMemory(r.memory ?? ""))
      .catch(() => setError(true));
    const t = setInterval(() => {
      getJSON<{ memory: string }>("/api/memory")
        .then((r) => setMemory(r.memory ?? ""))
        .catch(() => {});
    }, 5000);
    return () => clearInterval(t);
  }, []);

  return (
    <PageShell title="Memory">
      <p className="mb-4 text-[13.5px] text-ink-muted">
        What Friday remembers across sessions (MEMORY.md + USER.md). A frozen snapshot is injected
        into each run for prompt-cache stability.
      </p>
      {error ? (
        <p className="text-[13.5px] text-state-err">Backend not reachable.</p>
      ) : (
        <div className="md rounded-xl border border-edge-subtle bg-panel-elevated px-5 py-4 text-[14px] leading-relaxed text-ink">
          <ReactMarkdown>{memory || "_(no memory yet)_"}</ReactMarkdown>
        </div>
      )}
    </PageShell>
  );
}
