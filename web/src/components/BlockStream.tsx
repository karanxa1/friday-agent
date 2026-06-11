"use client";

import type { Block } from "@/lib/types";
import { ToolCard } from "./ToolCard";
import { Markdown } from "./Markdown";
import { SubagentFlow } from "./SubagentFlow";
import { CompactionChip } from "./CompactionChip";

/**
 * Renders an ordered run of reasoning blocks — thinking text, tool cards, and
 * nested sub-agent panels — so a sub-agent's work animates inline, recursively.
 * Shared by ReasoningFlow (top level) and SubagentFlow (each nested child).
 */
export function BlockStream({ blocks }: { blocks: Block[] }) {
  return (
    <>
      {blocks.map((b, i) => {
        if (b.kind === "thinking") {
          if (!b.text.trim()) return null;
          return (
            <div
              key={`t-${i}`}
              className="md md-think py-1 text-[13px] italic leading-relaxed text-ink-muted"
            >
              <Markdown>{b.text}</Markdown>
            </div>
          );
        }
        if (b.kind === "tool") {
          return <ToolCard key={b.card.id + i} card={b.card} />;
        }
        if (b.kind === "subagent") {
          return <SubagentFlow key={`s-${b.sub.id}-${i}`} sub={b.sub} />;
        }
        if (b.kind === "compaction") {
          return (
            <CompactionChip
              key={`k-${i}`}
              before={b.before}
              after={b.after}
              summarized={b.summarized}
            />
          );
        }
        // Plain text.
        return (
          <div key={`x-${i}`} className="md py-1 text-[13px] leading-relaxed text-ink-secondary">
            <Markdown>{b.text}</Markdown>
          </div>
        );
      })}
    </>
  );
}
