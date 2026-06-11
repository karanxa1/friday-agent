"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, Brain, Loader2, Check } from "@/components/icons";
import clsx from "clsx";
import type { Block } from "@/lib/types";
import { Markdown } from "./Markdown";

/**
 * The collapsible "Thinking… / Thought" container. It holds ONLY the model's
 * reasoning text — tool cards, sub-agents, generated images, file edits and
 * terminal output render as their own standalone blocks outside this dropdown
 * (see Message.tsx), so they stay visible even when the thought is collapsed.
 *
 * ``segments`` is a contiguous run of thinking blocks. Live (shimmer + spinner)
 * while any segment is still open; once they settle it shows "Thought" with a
 * check and auto-collapses once.
 */
export function ReasoningFlow({ segments }: { segments: Block[] }) {
  const active = segments.some((b) => b.kind === "thinking" && !b.done);

  const [open, setOpen] = useState(true);
  // Auto-collapse exactly once, when reasoning first finishes — never again, so
  // a user click can't be fought by a re-render during streaming.
  const collapsedOnce = useRef(false);

  useEffect(() => {
    if (!active && !collapsedOnce.current) {
      collapsedOnce.current = true;
      setOpen(false);
    }
  }, [active]);

  const label = active ? "Thinking…" : "Thought";

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      className="my-2 overflow-hidden rounded-xl border border-edge-subtle bg-panel-elevated/60 border-l-2 border-l-accent/40"
    >
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex h-10 w-full items-center gap-2.5 px-3 transition-colors hover:bg-panel-hover"
      >
        <Brain className="h-4 w-4 shrink-0 text-accent/70" />
        <span
          className={clsx(
            "text-[13.5px] font-medium",
            active
              ? "bg-[linear-gradient(90deg,#6e6e6e,rgba(255,255,255,0.6),#6e6e6e)] bg-[length:200%_100%] animate-shimmer bg-clip-text text-transparent"
              : "text-ink-secondary"
          )}
        >
          {label}
        </span>
        <span className="ml-auto flex items-center gap-2">
          {active ? (
            <Loader2 className="h-4 w-4 animate-spin text-accent/70" />
          ) : (
            <Check className="h-4 w-4 text-state-ok" />
          )}
          <ChevronDown
            className={clsx("h-4 w-4 text-ink-muted transition-transform duration-200", open && "rotate-180")}
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
            <div className="px-3 py-2">
              {segments.map((b, i) =>
                b.kind === "thinking" && b.text.trim() ? (
                  <div
                    key={`t-${i}`}
                    className="md md-think py-1 text-[13px] italic leading-relaxed text-ink-muted"
                  >
                    <Markdown>{b.text}</Markdown>
                  </div>
                ) : null
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
