# Friday

A self-modifying, self-learning autonomous agent built on **Google ADK** + **local Claude models** (Anthropic-protocol endpoint) + **MCP**.

## What it is

Friday is a general autonomous agent that can:

- **Plan → act → measure → adapt → learn** in a closed loop.
- **Edit its own code**, create new tools, author new MCP servers, and create skills — all git-backed and behind a human-approval gate.
- **Spawn sub-agents** recursively, routing easy work to Sonnet 4.6 and hard work to Opus 4.8.
- **See** (vision), **browse** (Playwright), and **search the web** (CallMissed) via MCP tools.
- **Remember** across sessions and **curate** its own skills over time (archive-only).

Flagship use case: a full **company social-media manager** (trend → content → publish → measure → adjust), runnable as the agent's first skill.

## Status

Local-first build in progress. See `architecture.md` for the design and `docs`/phase notes for progress.

## Quick start (dev)

```bash
uv venv --python 3.13 .venv
uv pip install -e ".[dev]"
cp .env.example .env   # local LLM + CallMissed keys
.venv/bin/python -m core.model --smoke   # smoke-test both model tiers
```

## Running

```bash
python -m cli serve --port 8080      # dashboard + API at http://localhost:8080
python -m cli run "your goal"        # one-shot agent run
python -m cli social --niche "developer tools"   # full social-media loop
python -m cli eval --case agent --runs 3         # evals harness
python -m cli curator                # archive-only skill lifecycle pass
```

See `demo_script.md` for the 2–3 minute walkthrough and `architecture.md` for the design.

## Deploy (Docker / Cloud Run)

Local container:
```bash
docker build -t friday:latest .
docker run -p 8080:8080 \
  -e FRIDAY_LLM_BASE_URL=... -e FRIDAY_LLM_API_KEY=... \
  -e CALLMISSED_API_KEY=... friday:latest
```

Google Cloud Run:
```bash
gcloud builds submit --tag gcr.io/$PROJECT/friday
gcloud run deploy friday \
  --image gcr.io/$PROJECT/friday \
  --port 8080 --allow-unauthenticated \
  --set-env-vars FRIDAY_LLM_BASE_URL=...,FRIDAY_MODEL_HARD=claude-opus-4-8,FRIDAY_MODEL_EASY=claude-sonnet-4-6 \
  --set-secrets FRIDAY_LLM_API_KEY=friday-llm-key:latest,CALLMISSED_API_KEY=callmissed-key:latest
```
> Note: the LLM endpoint must be reachable from Cloud Run (a public/VPC-accessible
> URL, not `localhost`). Store keys in Secret Manager, not env literals.

## Models

Uses a local Anthropic-protocol endpoint (default `http://localhost:8990`):
- **Hard tier**: `claude-opus-4-8`
- **Easy tier**: `claude-sonnet-4-6`

Configure via env (see `.env.example`).

## Safety

Every self-edit is git-committed and reversible. Publish, ad-spend, new auth, and self-modification all pass through a human-approval queue. Arbitrary code runs in a hardened Docker sandbox. See `architecture.md` § Safety.

## License

MIT (this project). Any upstream reference clones retain their own licenses.
