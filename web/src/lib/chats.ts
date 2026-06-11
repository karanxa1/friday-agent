import type { ChatMessage } from "./types";

/** Multi-session chat store in localStorage (newest first). */
export type ChatSession = {
  id: string;
  title: string;
  updatedAt: number;
  messages: ChatMessage[];
};

const KEY = "friday.chats.v1";
const LEGACY_KEY = "friday.chat.v1";
const MAX_SESSIONS = 30;
const MAX_MESSAGES = 80;

export const newSessionId = () => `c${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

let _rid = 0;
const _ridPrefix = Math.random().toString(36).slice(2, 7);

/**
 * Mark interrupted runs so nothing spins forever after a reload, AND reassign
 * a fresh unique id to every restored message. Older saved data used a counter
 * that reset to 0 each page load, so two sessions (or a session + new messages)
 * could share ids like "m1" — which makes React render duplicate turns. Giving
 * every restored message a guaranteed-unique id repairs that history in place.
 */
function sanitize(msgs: ChatMessage[]): ChatMessage[] {
  for (const m of msgs) {
    m.id = `r${_ridPrefix}_${++_rid}`;
    m.streaming = false;
    for (const b of m.blocks) {
      if (b.kind === "tool" && b.card.status === "running") {
        b.card.status = "error";
        b.card.result = b.card.result ?? "(interrupted — page was reloaded)";
      }
      if (b.kind === "thinking") b.done = true;
    }
  }
  return msgs;
}

export function titleFor(messages: ChatMessage[]): string {
  for (const m of messages) {
    if (m.role === "user") {
      const b = m.blocks.find((x) => x.kind === "text");
      if (b && b.kind === "text") return b.text.replace(/\s+/g, " ").slice(0, 48) || "New chat";
    }
  }
  return "New chat";
}

export function loadSessions(): ChatSession[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const sessions = JSON.parse(raw) as ChatSession[];
      for (const s of sessions) sanitize(s.messages);
      return sessions.sort((a, b) => b.updatedAt - a.updatedAt);
    }
    // Migrate the old single-chat history into a session once.
    const legacy = localStorage.getItem(LEGACY_KEY);
    if (legacy) {
      const messages = sanitize(JSON.parse(legacy) as ChatMessage[]);
      localStorage.removeItem(LEGACY_KEY);
      if (messages.length > 0) {
        const s: ChatSession = {
          id: newSessionId(),
          title: titleFor(messages),
          updatedAt: Date.now(),
          messages,
        };
        saveSessions([s]);
        return [s];
      }
    }
  } catch {
    /* corrupted store — start fresh */
  }
  return [];
}

export function saveSessions(sessions: ChatSession[]): void {
  const trimmed = sessions
    .slice()
    .sort((a, b) => b.updatedAt - a.updatedAt)
    .slice(0, MAX_SESSIONS)
    .map((s) => ({ ...s, messages: s.messages.slice(-MAX_MESSAGES) }));
  try {
    localStorage.setItem(KEY, JSON.stringify(trimmed));
  } catch {
    // quota exceeded — keep only the 5 most recent sessions
    try {
      localStorage.setItem(KEY, JSON.stringify(trimmed.slice(0, 5)));
    } catch {
      /* give up silently */
    }
  }
}

/** Insert or update one session and persist. Returns the new list (newest first). */
export function upsertSession(sessions: ChatSession[], session: ChatSession): ChatSession[] {
  const rest = sessions.filter((s) => s.id !== session.id);
  const next = [session, ...rest].sort((a, b) => b.updatedAt - a.updatedAt);
  saveSessions(next);
  return next;
}

export function deleteSession(sessions: ChatSession[], id: string): ChatSession[] {
  const next = sessions.filter((s) => s.id !== id);
  saveSessions(next);
  return next;
}

/** Bucket sessions by recency for the sidebar (Cursor-style groups). */
export function groupSessions(
  sessions: ChatSession[]
): { label: string; items: ChatSession[] }[] {
  const now = Date.now();
  const day = 86_400_000;
  const buckets: [string, (age: number) => boolean][] = [
    ["Today", (a) => a < day],
    ["Yesterday", (a) => a < 2 * day],
    ["This week", (a) => a < 7 * day],
    ["Older", () => true],
  ];
  const groups = new Map<string, ChatSession[]>();
  for (const s of sessions) {
    const age = now - s.updatedAt;
    const label = buckets.find(([, fits]) => fits(age))![0];
    (groups.get(label) ?? groups.set(label, []).get(label)!).push(s);
  }
  return buckets.filter(([l]) => groups.has(l)).map(([label]) => ({ label, items: groups.get(label)! }));
}

export function relativeTime(ts: number): string {
  const diff = Date.now() - ts;
  const min = Math.floor(diff / 60_000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d}d ago`;
  return new Date(ts).toLocaleDateString();
}
