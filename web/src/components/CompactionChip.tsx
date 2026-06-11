"use client";

import { motion } from "framer-motion";
import { Archive } from "lucide-react";

/**
 * A compact inline marker shown where the conversation history was summarized
 * to stay within the context window. Mirrors opencode's compaction indicator.
 */
export function CompactionChip({
  before,
  after,
  summarized,
}: {
  before: number;
  after: number;
  summarized: number;
}) {
  const fmt = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`);
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22 }}
      className="my-2 flex items-center gap-2 rounded-lg border border-edge-subtle bg-panel-elevated/50 px-3 py-1.5 text-[12px] text-ink-muted"
    >
      <Archive className="h-3.5 w-3.5 shrink-0 text-accent/60" />
      <span>
        Context compacted — summarized {summarized} earlier{" "}
        {summarized === 1 ? "turn" : "turns"} ({fmt(before)} → {fmt(after)} tokens)
      </span>
    </motion.div>
  );
}
