/** Normalize MCP-shaped tool results before they reach the UI.
 *
 * MCP servers return `{"content":[{"type":"text","text":"…"}],"isError":true}`;
 * rendering that raw JSON in a tool card is unreadable. Extract the inner text
 * and surface the error flag so the card styles itself correctly.
 */
export function normalizeToolResult(raw: string): { text: string; isError: boolean } {
  const s = (raw ?? "").trim();
  if (!s.startsWith("{")) return { text: raw, isError: false };
  try {
    const j = JSON.parse(s) as { content?: unknown; isError?: unknown };
    if (j && Array.isArray(j.content)) {
      const text = (j.content as Array<string | { text?: string }>)
        .map((c) => (typeof c === "string" ? c : (c?.text ?? "")))
        .filter(Boolean)
        .join("\n");
      if (text) return { text, isError: Boolean(j.isError) };
    }
  } catch {
    /* not JSON — fall through */
  }
  return { text: raw, isError: false };
}
