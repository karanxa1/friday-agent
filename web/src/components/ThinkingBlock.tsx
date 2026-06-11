"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, Brain, Loader2, Check } from "lucide-react";
import clsx from "clsx";

export function ThinkingBlock({ text, done }: { text: string; done: boolean }) {
  // Auto-collapse once thinking finishes; user can re-open.
  const [open, setOpen] = useState(true);
  const [userToggled, setUserToggled] = useState(false);

  useEffect(() => {
    if (done && !userToggled) setOpen(false);
  }, [done, userToggled]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      className="my-2 overflow-hidden rounded-xl border border-edge-subtle bg-panel-elevated/60 border-l-2 border-l-accent/40"
    >
      <button
        onClick={() => {
          setOpen((v) => !v);
          setUserToggled(true);
        }}
        className="flex h-10 w-full items-center gap-2.5 px-3 hover:bg-panel-hover transition-colors"
      >
        <Brain className="h-4 w-4 shrink-0 text-accent/70" />
        <span
          className={clsx(
            "text-[13.5px] font-medium",
            done ? "text-ink-secondary" : "bg-[linear-gradient(90deg,#6e6e6e,rgba(255,255,255,0.6),#6e6e6e)] bg-[length:200%_100%] animate-shimmer bg-clip-text text-transparent"
          )}
        >
          {done ? "Thought" : "Thinking…"}
        </span>
        <span className="ml-auto flex items-center gap-2">
          {!done ? (
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
            className="overflow-hidden"
          >
            <div className="max-h-[300px] overflow-auto border-t border-edge-subtle px-3.5 py-2.5 text-[13px] italic leading-relaxed text-ink-muted whitespace-pre-wrap">
              {text}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
