"use client";

import { motion } from "framer-motion";
import clsx from "clsx";
import type { Block, ChatMessage } from "@/lib/types";
import { ReasoningFlow } from "./ReasoningFlow";
import { ToolCard } from "./ToolCard";
import { SubagentFlow } from "./SubagentFlow";
import { CompactionChip } from "./CompactionChip";
import { Markdown } from "./Markdown";

// Group the assistant's blocks for rendering. ONLY consecutive thinking blocks
// collapse into a ReasoningFlow ("Thought" dropdown). Tool cards, sub-agent
// panels and compaction markers render as their own standalone, always-visible
// blocks — so generated images, file edits, terminal output and browser views
// stay visible even when the reasoning is collapsed.
type Group =
  | { kind: "reasoning"; blocks: Block[] }
  | { kind: "tool"; block: Extract<Block, { kind: "tool" }> }
  | { kind: "subagent"; block: Extract<Block, { kind: "subagent" }> }
  | { kind: "compaction"; block: Extract<Block, { kind: "compaction" }> }
  | { kind: "text"; block: Extract<Block, { kind: "text" }> };

function groupBlocks(blocks: Block[]): Group[] {
  const groups: Group[] = [];
  for (const b of blocks) {
    if (b.kind === "thinking") {
      const last = groups[groups.length - 1];
      if (last && last.kind === "reasoning") last.blocks.push(b);
      else groups.push({ kind: "reasoning", blocks: [b] });
    } else if (b.kind === "tool") {
      groups.push({ kind: "tool", block: b });
    } else if (b.kind === "subagent") {
      groups.push({ kind: "subagent", block: b });
    } else if (b.kind === "compaction") {
      groups.push({ kind: "compaction", block: b });
    } else {
      groups.push({ kind: "text", block: b });
    }
  }
  return groups;
}

export function Message({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      className="flex flex-col gap-1"
    >
      <div className="flex items-center gap-1.5 text-[12px] font-medium text-ink-muted">
        {isUser ? "You" : message.agent && message.agent !== "root" ? `Agent · ${message.agent}` : "Friday"}
      </div>

      {isUser ? (
        <div className="rounded-xl border border-edge-subtle bg-panel-elevated px-4 py-2.5 text-[14.5px] leading-relaxed text-ink">
          {message.blocks.map((b, i) =>
            b.kind === "text" ? <span key={i} className="whitespace-pre-wrap">{b.text}</span> : null
          )}
        </div>
      ) : (
        <div className="text-[14.5px] leading-[1.7] text-ink">
          {(() => {
            const groups = groupBlocks(message.blocks);
            return groups.map((g, i) => {
              if (g.kind === "reasoning") {
                return <ReasoningFlow key={`r-${i}`} segments={g.blocks} />;
              }
              if (g.kind === "tool") {
                return <ToolCard key={`c-${g.block.card.id}-${i}`} card={g.block.card} />;
              }
              if (g.kind === "subagent") {
                return <SubagentFlow key={`s-${g.block.sub.id}-${i}`} sub={g.block.sub} />;
              }
              if (g.kind === "compaction") {
                return (
                  <CompactionChip
                    key={`k-${i}`}
                    before={g.block.before}
                    after={g.block.after}
                    summarized={g.block.summarized}
                  />
                );
              }
              const isLast = i === groups.length - 1;
              return (
                <div key={`x-${i}`} className="md">
                  <Markdown>{g.block.text}</Markdown>
                  {message.streaming && isLast && (
                    <span className="inline-block h-[1.1em] w-[2px] translate-y-[2px] animate-caret bg-accent align-middle" />
                  )}
                </div>
              );
            });
          })()}
          {message.streaming && message.blocks.length === 0 && <ThinkingShimmer />}
        </div>
      )}
    </motion.div>
  );
}

function ThinkingShimmer() {
  return (
    <span
      className={clsx(
        "inline-block bg-clip-text text-transparent",
        "bg-[linear-gradient(90deg,#6e6e6e,rgba(255,255,255,0.55),#6e6e6e)]",
        "bg-[length:200%_100%] animate-shimmer text-[14.5px]"
      )}
    >
      Thinking…
    </span>
  );
}
