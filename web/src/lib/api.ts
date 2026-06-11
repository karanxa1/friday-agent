import type { StreamEvent } from "./types";

// Default to same-origin ("") so the browser calls /api on the current host
// (e.g. https://otpgod.com/api → Caddy → backend). Set NEXT_PUBLIC_FRIDAY_API
// only to target a different origin (e.g. http://localhost:8080 in dev).
const API_BASE = process.env.NEXT_PUBLIC_FRIDAY_API ?? "";
const url = (path: string) => `${API_BASE}${path}`;

// When the backend runs with FRIDAY_API_TOKEN set, the matching token is sent
// here so authenticated deployments work. Unset (local dev) = no header.
const API_TOKEN = process.env.NEXT_PUBLIC_FRIDAY_API_TOKEN ?? "";

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return API_TOKEN ? { ...extra, Authorization: `Bearer ${API_TOKEN}` } : extra;
}

/**
 * POST to an SSE endpoint and yield parsed StreamEvents as they arrive.
 * Uses fetch + ReadableStream (EventSource can't POST a body).
 */
export async function* streamChat(
  path: string,
  body: Record<string, unknown>,
  signal?: AbortSignal
): AsyncGenerator<StreamEvent> {
  const res = await fetch(url(path), {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
    signal,
  });
  if (!res.body) throw new Error("no response body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames separated by a blank line.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      const json = line.slice(5).trim();
      if (!json) continue;
      try {
        yield JSON.parse(json) as StreamEvent;
      } catch {
        // ignore malformed frame
      }
    }
  }
}

export async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(url(path), { headers: authHeaders() });
  return res.json() as Promise<T>;
}

export async function postJSON<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(url(path), {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  return res.json() as Promise<T>;
}

export async function putJSON<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(url(path), {
    method: "PUT",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  return res.json() as Promise<T>;
}

export async function deleteJSON<T>(path: string): Promise<T> {
  const res = await fetch(url(path), { method: "DELETE", headers: authHeaders() });
  return res.json() as Promise<T>;
}
