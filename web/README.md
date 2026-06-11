# Friday Web — Cursor-style chat frontend

A Next.js (App Router, TypeScript, Tailwind, framer-motion) chat UI for Friday,
styled after the Cursor AI IDE. **Everything streams**: tokens, tool calls, tool
results, and self-edits render live via SSE.

## Run

```bash
# 1. start the Friday backend (from ../friday)
cd ../friday && .venv/bin/python -m cli serve --port 8080

# 2. start the frontend
npm install
FRIDAY_API=http://localhost:8080 npm run dev   # http://localhost:3000
```

`next.config.js` proxies `/api/*` to `$FRIDAY_API` so the browser talks to the
backend without CORS issues.

## Features

- **Streaming chat** — token-by-token via `/api/chat/stream` (SSE over fetch).
- **Cursor-style tool cards** — collapsible cards with per-tool icons, a left
  status stripe (amber running → green done → red error), spinner→check
  animation, and an expandable monospace body showing args + result.
- **Agent picker** — switch between `root` and the social-media specialists
  (trend_scout, content_studio, analyst, publisher, ad_manager).
- **Side panel** — live pending-approval queue (approve/reject) + activity log.
- **Animations** (framer-motion) — message fade-in, thinking shimmer, streaming
  caret, tool-card expand/collapse, status crossfade.

## Structure

```
src/
├── app/            page.tsx (SSE consumer + chat state), layout, globals.css
├── components/     Message, ToolCard, Composer, SidePanel
└── lib/            api.ts (streamChat SSE client), types.ts
```
