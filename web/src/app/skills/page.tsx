"use client";

import { PageShell } from "@/components/AppNav";
import { SkillsPanel } from "@/components/SkillsPanel";

export default function SkillsPage() {
  return (
    <PageShell title="Skills">
      <p className="mb-4 text-[13.5px] text-ink-muted">
        Procedural memory: step-by-step playbooks Friday follows. Create your own or let Friday
        write them; agent-created skills are curated automatically (archive-only).
      </p>
      <div className="min-h-[60vh]">
        <SkillsPanel />
      </div>
    </PageShell>
  );
}
