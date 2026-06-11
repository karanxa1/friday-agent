"use client";

import { useEffect, useState } from "react";
import { Brain, Shield } from "lucide-react";
import clsx from "clsx";
import { PageShell } from "@/components/AppNav";
import { getJSON, postJSON } from "@/lib/api";
import type { AppConfig } from "@/lib/types";

const AUTONOMY_LEVELS: { value: string; label: string; desc: string }[] = [
  { value: "L0", label: "L0 — Ask everything", desc: "Every sensitive action waits for approval." },
  { value: "L1", label: "L1 — Balanced", desc: "Gated actions (publish, self-edit, spend) wait; the rest runs free." },
  { value: "L2", label: "L2 — Autonomous", desc: "Maximum autonomy; use with care." },
];

export default function SettingsPage() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    getJSON<AppConfig>("/api/config").then(setConfig).catch(() => setError(true));
  }, []);

  async function update(patch: Record<string, unknown>) {
    try {
      setConfig(await postJSON<AppConfig>("/api/config", patch));
    } catch {
      setError(true);
    }
  }

  return (
    <PageShell title="Settings">
      {error && <p className="mb-4 text-[13.5px] text-state-err">Backend not reachable.</p>}

      <section className="mb-6 rounded-xl border border-edge-subtle bg-panel-elevated p-5">
        <div className="mb-1 flex items-center gap-2 text-[15px] font-medium text-ink">
          <Brain className="h-4 w-4 text-accent" /> Extended thinking
        </div>
        <p className="mb-3 text-[13px] text-ink-muted">
          Stream the model&apos;s reasoning as a collapsible block before each answer (uses the
          -thinking model variants).
        </p>
        <button
          onClick={() => update({ thinking: !config?.thinking })}
          disabled={!config}
          className={clsx(
            "rounded-lg px-4 py-2 text-[13px] font-medium",
            config?.thinking ? "bg-accent text-[#0b1220]" : "bg-panel-active text-ink-secondary"
          )}
        >
          {config?.thinking ? "Thinking ON" : "Thinking OFF"}
        </button>
      </section>

      <section className="mb-6 rounded-xl border border-edge-subtle bg-panel-elevated p-5">
        <div className="mb-1 flex items-center gap-2 text-[15px] font-medium text-ink">
          <Shield className="h-4 w-4 text-state-run" /> Autonomy level
        </div>
        <p className="mb-3 text-[13px] text-ink-muted">
          How much Friday may do without asking. Self-edits, publishing, ad-spend, and new
          credentials always stay git-backed and auditable.
        </p>
        <div className="flex flex-col gap-2">
          {AUTONOMY_LEVELS.map((l) => (
            <button
              key={l.value}
              onClick={() => update({ autonomy: l.value })}
              disabled={!config}
              className={clsx(
                "rounded-lg border px-4 py-2.5 text-left",
                config?.autonomy === l.value
                  ? "border-accent/60 bg-accent/10"
                  : "border-edge-subtle hover:bg-panel-hover"
              )}
            >
              <span className={clsx("block text-[13.5px] font-medium", config?.autonomy === l.value ? "text-accent" : "text-ink")}>
                {l.label}
              </span>
              <span className="block text-[12px] text-ink-muted">{l.desc}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="rounded-xl border border-edge-subtle bg-panel-elevated p-5">
        <div className="mb-2 text-[15px] font-medium text-ink">Models</div>
        <div className="flex flex-col gap-1 font-mono text-[13px] text-ink-secondary">
          <span>hard tier · {config?.model_hard ?? "—"}</span>
          <span>easy tier · {config?.model_easy ?? "—"}</span>
        </div>
        <p className="mt-2 text-[12px] text-ink-muted">
          Configure via FRIDAY_MODEL_HARD / FRIDAY_MODEL_EASY env vars.
        </p>
      </section>
    </PageShell>
  );
}
