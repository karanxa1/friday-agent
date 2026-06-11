"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, Laptop, Menu, PanelRight } from "@/components/icons";
import clsx from "clsx";
import { Composer, type Attachment } from "@/components/Composer";
import { Message } from "@/components/Message";
import { Sidebar } from "@/components/Sidebar";
import { SidePanel } from "@/components/SidePanel";
import { deleteJSON, getJSON, postJSON, streamChat } from "@/lib/api";
import {
  deleteSession,
  loadSessions,
  newSessionId,
  titleFor,
  upsertSession,
  type ChatSession,
} from "@/lib/chats";
import { normalizeToolResult } from "@/lib/toolResult";
import type { AppConfig, Block, ChatMessage, StreamEvent, Subagent } from "@/lib/types";

// Per-load random prefix + monotonic counter → ids never collide with ids
// restored from a previous load (where the counter started over at 0).
let idc = 0;
const ID_PREFIX = Math.random().toString(36).slice(2, 7);
const newId = () => `m${ID_PREFIX}_${++idc}`;

const SUGGESTIONS = [
  "Find trends in developer tools",
  "Create a tool that reverses text",
  "Grow launch awareness this week",
  "Write a skill for weekly reports",
];

// ── sub-agent aware block routing ─────────────────────────────────────────
// Events carry an optional `depth`: 0 (or absent) = the main agent, ≥1 = a
// nested sub-agent. We descend into the deepest still-open sub-agent and apply
// the event to *its* block stream, so a child's thinking/tools/sub-agents all
// render nested and animated inside the parent.

/** The block list an incoming (sub-)agent event should append to. */
function activeBlocks(blocks: Block[]): Block[] {
  for (let i = blocks.length - 1; i >= 0; i--) {
    const b = blocks[i];
    if (b.kind === "subagent" && !b.sub.done) return activeBlocks(b.sub.blocks);
  }
  return blocks;
}

/** Find a tool card by id anywhere in the tree (results can arrive out of
 * order relative to a sub-agent closing), returning a mutable handle. */
function findCard(blocks: Block[], id: string): Extract<Block, { kind: "tool" }> | null {
  for (const b of blocks) {
    if (b.kind === "tool" && b.card.id === id) return b;
    if (b.kind === "subagent") {
      const hit = findCard(b.sub.blocks, id);
      if (hit) return hit;
    }
  }
  return null;
}

/** Close the deepest open sub-agent matching `id` (or the deepest open one). */
function closeSubagent(blocks: Block[], id: string): boolean {
  for (let i = blocks.length - 1; i >= 0; i--) {
    const b = blocks[i];
    if (b.kind === "subagent" && !b.sub.done) {
      if (closeSubagent(b.sub.blocks, id)) return true; // a deeper one owns it
      b.sub.done = true;
      return true;
    }
  }
  return false;
}

/** Apply one stream event into a (deeply) mutable copy of the message blocks. */
function applyToBlocks(root: Block[], ev: StreamEvent): void {
  // subagent_start nests a new container under the current active scope.
  if (ev.type === "subagent_start") {
    const target = activeBlocks(root);
    const sub: Subagent = {
      id: ev.id,
      agent: ev.agent,
      depth: ev.depth,
      task: ev.task,
      role: ev.role,
      tier: ev.tier,
      done: false,
      blocks: [],
    };
    target.push({ kind: "subagent", sub });
    return;
  }
  if (ev.type === "subagent_end") {
    closeSubagent(root, ev.id);
    return;
  }
  if (ev.type === "compaction") {
    activeBlocks(root).push({
      kind: "compaction",
      before: ev.tokens_before,
      after: ev.tokens_after,
      summarized: ev.summarized,
    });
    return;
  }
  // tool_result matches by id anywhere (order-independent across nesting).
  if (ev.type === "tool_result") {
    const hit = findCard(root, ev.id);
    if (hit) {
      const norm = normalizeToolResult(ev.result);
      hit.card = {
        ...hit.card,
        result: norm.text,
        status: ev.ok && !norm.isError ? "done" : "error",
        media: ev.media,
      };
    }
    return;
  }

  const blocks = activeBlocks(root);
  const last = blocks[blocks.length - 1];

  switch (ev.type) {
    case "thinking_start":
      blocks.push({ kind: "thinking", text: "", done: false });
      return;
    case "thinking": {
      for (let i = blocks.length - 1; i >= 0; i--) {
        const b = blocks[i];
        if (b.kind === "thinking" && !b.done) {
          b.text += ev.text;
          return;
        }
      }
      blocks.push({ kind: "thinking", text: ev.text, done: false });
      return;
    }
    case "thinking_end": {
      for (let i = blocks.length - 1; i >= 0; i--) {
        const b = blocks[i];
        if (b.kind === "thinking" && !b.done) {
          b.done = true;
          return;
        }
      }
      return;
    }
    case "token":
      if (last && last.kind === "text") last.text += ev.text;
      else blocks.push({ kind: "text", text: ev.text });
      return;
    case "message":
      blocks.push({ kind: "text", text: ev.text });
      return;
    case "tool_args": {
      for (let i = blocks.length - 1; i >= 0; i--) {
        const b = blocks[i];
        if (b.kind === "tool" && b.card.name === ev.name && b.card.id.startsWith("pending_")) {
          b.card = { ...b.card, argsPreview: (b.card.argsPreview ?? "") + ev.delta };
          return;
        }
      }
      blocks.push({
        kind: "tool",
        card: {
          id: `pending_${ev.name}_${blocks.length}`,
          name: ev.name,
          args: {},
          status: "running",
          argsPreview: ev.delta,
        },
      });
      return;
    }
    case "tool_call": {
      for (let i = blocks.length - 1; i >= 0; i--) {
        const b = blocks[i];
        if (b.kind === "tool" && b.card.name === ev.name && b.card.id.startsWith("pending_")) {
          b.card = { id: ev.id, name: ev.name, args: ev.args, status: "running" };
          return;
        }
      }
      blocks.push({
        kind: "tool",
        card: { id: ev.id, name: ev.name, args: ev.args, status: "running" },
      });
      return;
    }
    default:
      return;
  }
}

export default function Home() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentId, setCurrentId] = useState<string>("");
  const [navOpen, setNavOpen] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [agent, setAgent] = useState("root");
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getJSON<AppConfig>("/api/config").then(setConfig).catch(() => {});
    const loaded = loadSessions();
    setSessions(loaded);
    // Resume the most recent chat, or start fresh.
    if (loaded.length > 0) {
      setCurrentId(loaded[0].id);
      setMessages(loaded[0].messages);
    } else {
      setCurrentId(newSessionId());
    }
  }, []);

  // Persist the active conversation into its session on every change.
  useEffect(() => {
    if (!currentId || messages.length === 0) return;
    setSessions((prev) =>
      upsertSession(prev, {
        id: currentId,
        title: titleFor(messages),
        updatedAt: Date.now(),
        messages,
      })
    );
  }, [messages, currentId]);

  const newChat = useCallback(() => {
    abortRef.current?.abort();
    setStreaming(false);
    setMessages([]);
    setCurrentId(newSessionId());
  }, []);

  // ⌘N / Ctrl+N starts a new chat (when the browser lets us intercept it).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "n") {
        e.preventDefault();
        newChat();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [newChat]);

  const openChat = useCallback(
    (id: string) => {
      if (id === currentId) return;
      abortRef.current?.abort();
      setStreaming(false);
      const s = sessions.find((x) => x.id === id);
      if (!s) return;
      setCurrentId(id);
      setMessages(s.messages);
    },
    [currentId, sessions]
  );

  const deleteChat = useCallback(
    (id: string) => {
      deleteJSON(`/api/chat/${id}`).catch(() => {}); // free the backend conversation
      setSessions((prev) => {
        const next = deleteSession(prev, id);
        if (id === currentId) {
          abortRef.current?.abort();
          setStreaming(false);
          if (next.length > 0) {
            setCurrentId(next[0].id);
            setMessages(next[0].messages);
          } else {
            setCurrentId(newSessionId());
            setMessages([]);
          }
        }
        return next;
      });
    },
    [currentId]
  );

  const toggleThinking = useCallback(async () => {
    if (!config) return;
    try {
      setConfig(await postJSON<AppConfig>("/api/config", { thinking: !config.thinking }));
    } catch {
      // backend not up
    }
  }, [config]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const applyEvent = useCallback((asstId: string, ev: StreamEvent) => {
    setMessages((prev) =>
      prev.map((m) => {
        if (m.id !== asstId) return m;
        // Deep-clone so nested sub-agent blocks are safely mutable, then route
        // the event to the right (possibly nested) container.
        const blocks: Block[] = structuredClone(m.blocks);
        applyToBlocks(blocks, ev);
        // Only the top-level (depth 0) agent labels the message bubble.
        const evDepth = (ev as { depth?: number }).depth ?? 0;
        const agent = "agent" in ev && evDepth === 0 ? ev.agent : m.agent;
        return { ...m, blocks, agent };
      })
    );
  }, []);

  const send = useCallback(
    async (text: string, attachments: Attachment[] = []) => {
      const shownText =
        attachments.length > 0
          ? `${text}\n\n📎 ${attachments.map((a) => a.name).join(" · ")}`
          : text;
      const userMsg: ChatMessage = {
        id: newId(),
        role: "user",
        blocks: [{ kind: "text", text: shownText }],
      };
      const asstId = newId();
      const asstMsg: ChatMessage = { id: asstId, role: "assistant", blocks: [], streaming: true };
      setMessages((p) => [...p, userMsg, asstMsg]);
      setStreaming(true);

      const ac = new AbortController();
      abortRef.current = ac;
      const path = agent === "root" ? "/api/chat/stream" : "/api/agent/stream";
      // session_id keeps one continuous backend conversation per chat, so the
      // agent remembers earlier turns, file edits, and tool results.
      const body =
        agent === "root"
          ? { goal: text, session_id: currentId, attachments }
          : { message: text, agent, session_id: currentId, attachments };

      try {
        for await (const ev of streamChat(path, body, ac.signal)) {
          if (ev.type === "error") {
            applyEvent(asstId, { type: "message", text: `**Error:** ${ev.message}`, agent });
            break;
          }
          if (ev.type === "done") break;
          applyEvent(asstId, ev);
        }
      } catch (e) {
        if (!(e instanceof DOMException && e.name === "AbortError")) {
          applyEvent(asstId, { type: "message", text: `**Stream error:** ${String(e)}`, agent });
        }
      } finally {
        setMessages((p) => p.map((m) => (m.id === asstId ? { ...m, streaming: false } : m)));
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [agent, applyEvent, currentId]
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setStreaming(false);
  }, []);

  const empty = messages.length === 0;
  const modelLabel = config ? `${config.model_hard} / ${config.model_easy}` : "…";

  return (
    <div className="flex h-screen bg-panel">
      <Sidebar
        sessions={sessions}
        currentId={currentId}
        onOpenChat={openChat}
        onNewChat={newChat}
        onDeleteChat={deleteChat}
        modelLabel={modelLabel}
        mobileOpen={navOpen}
        onCloseMobile={() => setNavOpen(false)}
      />

      <div className="relative flex min-w-0 flex-1 flex-col">
        {/* slim header: hamburger (mobile) + title + panel toggle */}
        <header
          className={clsx(
            "flex h-12 shrink-0 items-center gap-2 px-3 sm:px-4",
            !empty && "border-b border-edge-subtle"
          )}
        >
          <button
            onClick={() => setNavOpen(true)}
            title="Menu"
            className="flex h-8 w-8 items-center justify-center rounded-md text-ink-muted hover:bg-panel-hover hover:text-ink lg:hidden"
          >
            <Menu className="h-4 w-4" />
          </button>
          {!empty && (
            <span className="min-w-0 truncate text-[13.5px] font-medium text-ink-secondary">
              {titleFor(messages)}
            </span>
          )}
          <span className="ml-auto flex items-center gap-2">
            <button
              onClick={() => setPanelOpen((v) => !v)}
              title="Approvals & activity"
              className="flex h-8 w-8 items-center justify-center rounded-md text-ink-muted hover:bg-panel-hover hover:text-ink lg:hidden"
            >
              <PanelRight className="h-4 w-4" />
            </button>
          </span>
        </header>

        {empty ? (
          /* ── hero (Cursor-style home) ── */
          <div className="flex flex-1 flex-col">
            <div className="flex flex-1 flex-col items-center justify-center px-4 pb-16">
              <div className="w-full max-w-2xl">
                <div className="mb-4 flex items-center justify-center gap-2.5 text-[13.5px]">
                  <span className="flex items-center gap-1 font-medium text-ink">
                    Home <ChevronDown className="h-3.5 w-3.5 text-ink-muted" />
                  </span>
                  <span className="flex items-center gap-1.5 text-ink-secondary">
                    <Laptop className="h-3.5 w-3.5" /> Local
                  </span>
                </div>
                <Composer
                  variant="hero"
                  onSend={send}
                  onStop={stop}
                  streaming={streaming}
                  agent={agent}
                  setAgent={setAgent}
                  thinkingOn={config?.thinking}
                  onToggleThinking={toggleThinking}
                />
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => send(s)}
                      className="rounded-full border border-edge-subtle bg-panel-elevated px-3.5 py-1.5 text-[12.5px] text-ink-secondary hover:border-accent/50 hover:text-ink"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <p className="pb-5 text-center text-[12px] text-ink-muted/70">
              Friday can search the web, edit files, build tools and run code — gated actions wait
              in{" "}
              <span className="rounded bg-panel-active px-1.5 py-0.5 font-mono text-[11px]">
                Approvals
              </span>
            </p>
          </div>
        ) : (
          /* ── active chat ── */
          <>
            <div ref={scrollRef} className="flex-1 overflow-y-auto overflow-x-hidden">
              <div className="mx-auto flex w-full min-w-0 max-w-3xl flex-col gap-5 px-3 py-4 sm:px-5 sm:py-6">
                {messages.map((m) => (
                  <Message key={m.id} message={m} />
                ))}
              </div>
            </div>
            <div className="px-3 pb-3 pt-2 sm:px-5 sm:pb-4">
              <div className="mx-auto w-full max-w-3xl">
                <Composer
                  onSend={send}
                  onStop={stop}
                  streaming={streaming}
                  agent={agent}
                  setAgent={setAgent}
                  thinkingOn={config?.thinking}
                  onToggleThinking={toggleThinking}
                />
                <p className="mt-1.5 text-center text-[11px] text-ink-muted/70">
                  Enter to send · Shift+Enter for a new line
                </p>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Desktop: docked side panel */}
      <div className="hidden lg:block">
        <SidePanel />
      </div>

      {/* Mobile: slide-over drawer */}
      {panelOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setPanelOpen(false)} />
          <div className="absolute right-0 top-0 h-full">
            <SidePanel />
          </div>
        </div>
      )}
    </div>
  );
}
