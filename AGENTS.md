# Working agreement for this repo (hack-agent / Friday)

## Workflow rule — ALWAYS plan → todo → implement (MANDATORY, NO EXCEPTIONS)

Before implementing ANYTHING, you MUST first state a plan and create a tracked
todo list. This is required for every change — never start editing code before
the plan and todo exist. Follow this order and do not skip steps:

1. **Plan.** Write a short plan first: what you're going to change, which files,
   and the approach. State it before touching code.
2. **Todo.** Break the plan into a tracked todo list (use the task/todo tools).
   One item per discrete, verifiable unit of work. Always create the todo list
   before the first edit, even for small multi-step changes.
3. **Implement.** Work the todo list top to bottom. Mark each item in-progress
   when you start it and completed only when it actually works (tests/build
   green — never on a partial or failing state).
4. **Verify.** Before claiming done, run the relevant checks:
   - Backend: `cd friday && .venv/bin/python -m pytest tests/ -q`
   - Frontend: `cd web && npm run build`

Only a truly trivial single-line edit (e.g. a typo fix) may skip the formal
plan/todo — but still verify. When in doubt, write the plan and todo.

## Project layout

- `friday/` — Python backend (FastAPI control plane, agent core, tools). Python 3.13.
- `web/` — Next.js 15 / React 19 frontend (Cursor-style streaming chat UI).
- `reference/hermes-agent/` — read-only design reference; never edit.

## Conventions

- New native tools register into a toolset via `@tool("<toolset>")` in their
  module, and the module is added to `_TOOL_MODULES` in
  `control_plane/builder.py`. Add the toolset to the agent in
  `registry/agents.json`. Cover new tools with a `tests/test_pNN_*.py` file.
- Sensitive actions (self-edits, publishing, new credentials/tools, ad-spend)
  stay behind the approval queue and are git-backed.
- Secrets never enter model context; scrub them in audit logs.
- Keep the SSE event contract in `control_plane/streaming.py` in sync with the
  frontend types in `web/src/lib/types.ts`.
