"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, Bot, Loader2, Check } from "@/components/icons";
import clsx from "clsx";
import type { Subagent } from "@/lib/types";
import { BlockStream } from "./BlockStream";

/**
 * A nested, animated panel for a delegated sub-agent. Shows the child's task,
 * tier badge, and live status, with its full block stream (thinking + tools +
 * any deeper sub-agents) rendered inside — so you watch the sub-agent work in
 * real time. Auto-collapses once (ref-guarded) when it finishes, but the click
 * toggle always wins.
 */
export function SubagentFlow({ sub }: { sub: Subagent }) {
  const active = !sub.done;
  const [open, setOpen] = useState(true);
  const collapsedOnce = useRef(false);

  useEffect(() => {
    if (!active && !collapsedOnce.current) {
      collapsedOnce.current = true;
      setOpen(false);
    }
  }, [active]);

  const tools = sub.blocks.filter((b) => b.kind === "tool").length;
  const kids = sub.blocks.filter((b) => b.kind === "subagent").length;
  const parts = [
    tools > 0 ? `${tools} tool${tools > 1 ? "s" : ""}` : "",
    kids > 0 ? `${kids} sub-agent${kids > 1 ? "s" : ""}` : "",
  ].filter(Boolean);
  const summary = parts.length ? ` · ${parts.join(" · ")}` : "";

  // Indent deeper levels slightly so nesting reads at a glance.
  return (
    <motion.div
      initial={{ opacity: 0, x: 6 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      className={clsx(
        "my-2 overflow-hidden rounded-xl border border-edge-subtle bg-panel-elevated/40",
        "border-l-2 border-l-violet-400/50"
      )}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors hover:bg-panel-hover"
      >
        <Bot className="h-4 w-4 shrink-0 text-violet-400/80" />
        <span className="flex min-w-0 flex-col">
          <span
            className={clsx(
              "truncate text-[13px] font-medium",
              active
                ? "bg-[linear-gradient(90deg,#8b7bd8,rgba(255,255,255,0.7),#8b7bd8)] bg-[length:200%_100%] animate-shimmer bg-clip-text text-transparent"
                : "text-ink-secondary"
            )}
          >
            {active ? "Sub-agent working" : "Sub-agent done"}
            {summary}
          </span>
          <span className="truncate text-[11.5px] text-ink-muted">{sub.task}</span>
        </span>
        <span className="ml-auto flex shrink-0 items-center gap-2">
          {sub.tier && (
            <span className="rounded-full border border-edge-subtle px-1.5 py-0.5 font-mono text-[10px] uppercase text-ink-muted">
              {sub.tier}
            </span>
          )}
          {active ? (
            <Loader2 className="h-4 w-4 animate-spin text-violet-400/80" />
          ) : (
            <Check className="h-4 w-4 text-state-ok" />
          )}
          <ChevronDown
            className={clsx(
              "h-4 w-4 text-ink-muted transition-transform duration-200",
              open && "rotate-180"
            )}
          />
        </span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeInOut" }}
            className="overflow-hidden border-t border-edge-subtle"
          >
            <div className="px-3 py-2 pl-4">
              {sub.blocks.length === 0 ? (
                <div className="py-1 text-[12px] italic text-ink-muted">starting…</div>
              ) : (
                <BlockStream blocks={sub.blocks} />
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
