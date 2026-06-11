"use client";

import { type ComponentType, useCallback, useEffect, useState } from "react";
import clsx from "clsx";
import { PageShell } from "@/components/AppNav";
import { Markdown } from "@/components/Markdown";
import { getJSON, postJSON } from "@/lib/api";
import { AlertCircle, Bot, CheckCircle2, Loader2 } from "@/components/icons";

type TaskSummary = {
  id: string;
  goal: string;
  status: string;
  created?: string;
  finished?: string | null;
  error?: string | null;
  events: number;
  tool_calls: number;
};

type TaskFull = TaskSummary & { output: string };

const STATUS: Record<
  string,
  { label: string; cls: string; Icon: ComponentType<{ className?: string }>; spin: boolean }
> = {
  running: { label: "Running", cls: "text-amber-400", Icon: Loader2, spin: true },
  done: { label: "Done", cls: "text-emerald-400", Icon: CheckCircle2, spin: false },
  error: { label: "Error", cls: "text-red-400", Icon: AlertCircle, spin: false },
  interrupted: { label: "Interrupted", cls: "text-ink-muted", Icon: AlertCircle, spin: false },
};

export default function TasksPage() {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [goal, setGoal] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [detail, setDetail] = useState<TaskFull | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await getJSON<{ tasks: TaskSummary[] }>("/api/tasks");
      setTasks(r.tasks);
    } catch {
      /* transient */
    }
  }, []);

  useEffect(() => {
    refresh();
    const i = setInterval(refresh, 3000);
    return () => clearInterval(i);
  }, [refresh]);

  useEffect(() => {
    if (!open) {
      setDetail(null);
      return;
    }
    let active = true;
    const load = async () => {
      try {
        const d = await getJSON<TaskFull>(`/api/tasks/${open}`);
        if (active) setDetail(d);
      } catch {
        /* transient */
      }
    };
    load();
    const i = setInterval(load, 2000);
    return () => {
      active = false;
      clearInterval(i);
    };
  }, [open]);

  const launch = async () => {
    if (!goal.trim() || busy) return;
    setBusy(true);
    try {
      await postJSON("/api/tasks", { goal });
      setGoal("");
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  return (
    <PageShell title="Tasks">
      <p className="mb-4 text-[13.5px] text-ink-muted">
        Launch an autonomous task. Friday runs it in the background on its own computer — it keeps
        going even if you close this tab. Come back any time to see progress and results.
      </p>

      <div className="mb-5 flex gap-2">
        <textarea
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="e.g. Research the top 5 AI agent frameworks and write me a PDF comparison"
          rows={2}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) launch();
          }}
          className="flex-1 resize-none rounded-lg border border-edge-strong bg-panel px-3 py-2 text-[13.5px] text-ink outline-none focus:border-accent/50"
        />
        <button
          onClick={launch}
          disabled={busy || !goal.trim()}
          className="flex items-center gap-1.5 self-end rounded-lg border border-accent/60 bg-accent/10 px-4 py-2 text-[13px] font-medium text-accent transition-colors hover:bg-accent/20 disabled:opacity-40"
        >
          <Bot className="h-4 w-4" /> Launch
        </button>
      </div>

      <div className="space-y-2">
        {tasks.length === 0 && <p className="text-[13px] text-ink-muted">No tasks yet.</p>}
        {tasks.map((t) => {
          const s = STATUS[t.status] ?? STATUS.interrupted;
          const isOpen = open === t.id;
          return (
            <div key={t.id} className="rounded-lg border border-edge-subtle bg-panel">
              <button
                onClick={() => setOpen(isOpen ? null : t.id)}
                className="flex w-full items-center gap-3 px-3 py-2.5 text-left"
              >
                <s.Icon className={clsx("h-4 w-4 shrink-0", s.cls, s.spin && "animate-spin")} />
                <span className="flex-1 truncate text-[13.5px] text-ink">{t.goal}</span>
                <span className="text-[11px] text-ink-muted">{t.tool_calls} tools</span>
                <span className={clsx("text-[11.5px]", s.cls)}>{s.label}</span>
              </button>
              {isOpen && detail && (
                <div className="border-t border-edge-subtle px-3 py-3">
                  {detail.error && <p className="mb-2 text-[12.5px] text-red-400">{detail.error}</p>}
                  {detail.output ? (
                    <div className="text-[13px] text-ink-secondary">
                      <Markdown>{detail.output}</Markdown>
                    </div>
                  ) : (
                    <p className="text-[12.5px] text-ink-muted">Working…</p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </PageShell>
  );
}
