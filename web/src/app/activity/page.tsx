"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { PageShell } from "@/components/AppNav";
import { getJSON } from "@/lib/api";
import { auditRowKey, type AuditEvent } from "@/lib/types";

const FILTERS = [
  "all",
  "run.",
  "stream.",
  "skill.",
  "files.",
  "web.",
  "browser.",
  "artifacts.",
  "todo.",
  "spawn.",
  "task.",
  "automation.",
  "approval.",
  "config.",
];

export default function ActivityPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    const fetchEvents = () => {
      const q = filter === "all" ? "" : `&prefix=${filter}`;
      getJSON<{ events: AuditEvent[] }>(`/api/audit?limit=200${q}`)
        .then((r) => setEvents((r.events ?? []).slice().reverse()))
        .catch(() => {});
    };
    fetchEvents();
    const t = setInterval(fetchEvents, 3000);
    return () => clearInterval(t);
  }, [filter]);

  return (
    <PageShell title="Activity">
      <div className="mb-4 flex flex-wrap gap-1.5">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={
              "rounded-full border px-3 py-1 text-[12px] " +
              (filter === f
                ? "border-accent/50 bg-accent/10 text-accent"
                : "border-edge-subtle text-ink-muted hover:text-ink-secondary")
            }
          >
            {f}
          </button>
        ))}
      </div>
      <div className="rounded-xl border border-edge-subtle bg-panel-elevated">
        {events.length === 0 ? (
          <p className="px-4 py-6 text-[13.5px] text-ink-muted">No events.</p>
        ) : (
          events.map((e, i) => {
            const extras = Object.entries(e).filter(([k]) => !["id", "ts", "event"].includes(k));
            return (
              <motion.div
                key={auditRowKey(e)}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: Math.min(i * 0.01, 0.3) }}
                className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 border-b border-edge-subtle px-4 py-2 font-mono text-[12.5px] last:border-b-0"
              >
                <span className="shrink-0 text-ink-muted/60">
                  {new Date(e.ts * 1000).toLocaleTimeString()}
                </span>
                <span className="shrink-0 font-medium text-ink-secondary">{e.event}</span>
                <span className="min-w-0 truncate text-ink-muted">
                  {extras.map(([k, v]) => `${k}=${String(v).slice(0, 60)}`).join("  ")}
                </span>
              </motion.div>
            );
          })
        )}
      </div>
    </PageShell>
  );
}
