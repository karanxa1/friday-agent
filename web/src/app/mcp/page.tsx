"use client";

import { PageShell } from "@/components/AppNav";
import { McpPanel } from "@/components/McpPanel";

export default function McpPage() {
  return (
    <PageShell title="MCP servers">
      <p className="mb-4 text-[13.5px] text-ink-muted">
        Bring-your-own-tools: register MCP servers and attach them to agents. Friday can also
        author its own MCP servers at runtime (approval-gated).
      </p>
      <div className="min-h-[60vh]">
        <McpPanel />
      </div>
    </PageShell>
  );
}
