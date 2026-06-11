// Normalized stream event types (must match control_plane/streaming.py)

export type StreamEvent =
  | { type: "start"; agent: string }
  | { type: "thinking_start"; agent: string; depth?: number }
  | { type: "thinking"; text: string; agent: string; depth?: number }
  | { type: "thinking_end"; agent: string; depth?: number }
  | { type: "token"; text: string; agent: string; depth?: number }
  | { type: "tool_args"; name: string; delta: string; agent: string; depth?: number }
  | {
      type: "tool_call";
      id: string;
      name: string;
      args: Record<string, unknown>;
      agent: string;
      depth?: number;
    }
  | {
      type: "tool_result";
      id: string;
      name: string;
      result: string;
      ok: boolean;
      agent: string;
      depth?: number;
      media?: ToolMedia;
    }
  | {
      type: "subagent_start";
      id: string;
      agent: string;
      depth: number;
      task: string;
      role?: string;
      tier?: string;
    }
  | { type: "subagent_end"; id: string; agent: string; depth: number }
  | {
      type: "compaction";
      agent: string;
      tokens_before: number;
      tokens_after: number;
      summarized: number;
      kept: number;
    }
  | { type: "message"; text: string; agent: string; depth?: number }
  | { type: "done"; tool_calls: number; chars: number }
  | { type: "error"; message: string };

/** Renderable media extracted from MCP tool results (images, interactive HTML). */
export type ToolMedia = {
  images: { mime: string; data: string }[];
  html: string[];
  /** External app URLs from MCP-UI `text/uri-list` resources (iframe src). */
  uris?: string[];
};

export type ToolCard = {
  id: string;
  name: string;
  args: Record<string, unknown>;
  result?: string;
  status: "running" | "done" | "error";
  media?: ToolMedia;
  /** Raw argument JSON accumulating while the model writes the call (live preview). */
  argsPreview?: string;
};

// A streamed assistant turn: interleaved text, thinking, tool cards, nested
// sub-agent runs, and compaction markers — in order.
export type Block =
  | { kind: "text"; text: string }
  | { kind: "thinking"; text: string; done: boolean }
  | { kind: "tool"; card: ToolCard }
  | { kind: "subagent"; sub: Subagent }
  | { kind: "compaction"; before: number; after: number; summarized: number };

/** A delegated sub-agent run: its own block stream, rendered nested + animated. */
export type Subagent = {
  id: string;
  agent: string;
  depth: number;
  task: string;
  role?: string;
  tier?: string;
  done: boolean;
  blocks: Block[];
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  blocks: Block[];
  streaming?: boolean;
  agent?: string;
};

export type PendingApproval = {
  id: string;
  type: string;
  summary: string;
  status: string;
  payload?: Record<string, unknown>;
};

export type SkillInfo = {
  name: string;
  description: string;
  created_by: string;
  pinned: boolean;
};

export type AppConfig = {
  thinking: boolean;
  autonomy: string;
  model_hard: string;
  model_easy: string;
};

export type AuditEvent = { id: string; ts: number; event: string; [k: string]: unknown };

/** Stable React key — legacy audit rows reused entity id as event id. */
export const auditRowKey = (e: AuditEvent) => `${e.ts}:${e.event}:${e.id}`;
