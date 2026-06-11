# Friday — Demo Script (2–3 min)

A tight run that shows the autonomous loop + the self-extension + MCP angle.

## 0. Setup (once)
```bash
cd friday
uv venv --python 3.13 .venv
uv pip install -e ".[dev]"
cp .env.example .env        # local LLM + CallMissed keys already filled in the example
.venv/bin/python -m core.model --smoke   # both tiers reply PONG
```

## 1. Start the dashboard (the "agents at work" view)
```bash
.venv/bin/python -m cli serve --port 8080
# open http://localhost:8080
```
Point out: run box, **pending-approval queue**, skills, memory, curator, audit log.

## 2. The autonomous social-media loop (trend → content → publish → measure → adjust)
In the dashboard click **"Run social-media loop"** (or CLI):
```bash
.venv/bin/python -m cli social --niche "developer tools / AI coding agents"
```
Narrate as stages stream into the audit log:
- **Trend Scout** calls the real **CallMissed web_search MCP** → ranked trends.
- **Content Studio** turns them into on-brand X/LinkedIn/Instagram drafts.
- **Publisher** queues 3–4 posts — **nothing publishes**; they appear in the
  approval queue (safety = feature).
- **Analyst** (Opus) reads mock metrics via the **metrics MCP** → pause/scale/
  reallocate recommendations with numbers.
- **Ad Manager** drafts budget changes — also queued, gated.

## 3. Human-in-the-loop approval
In the dashboard, **approve** one queued post and **reject** another. Show the
audit log recording each decision. Approved publish → lands in the sandbox store.

## 4. MCP extensibility, live (the "bring your own tools" moment)
Ask Friday to add a tool to itself:
```bash
.venv/bin/python -m cli run "Create a tool named 'reverse_text' in toolset 'custom' that returns its input reversed, then tell me the approval id."
```
Approve it in the dashboard, then:
```bash
.venv/bin/python -m cli run "Use apply_capability with that id, then call reverse_text on 'friday'."
```
Show the new tool was authored, gated, git-committed, hot-loaded, and called —
without a restart.

## 5. Self-learning (skills + curator)
```bash
.venv/bin/python -m cli run "Create a skill 'launch-week-playbook' capturing the steps we just used to grow launch awareness."
.venv/bin/python -m cli curator     # archive-only lifecycle pass
```

## 6. Safety + sandbox (optional)
```bash
.venv/bin/python -m cli run "Run python in the sandbox that prints 2**20, then try to reach the network."
```
Network call fails (`--network none`); compute succeeds — isolation shown.

## 7. Evals (reliability + economics)
```bash
.venv/bin/python -m cli eval --case agent --runs 3
```
Show success rate / avg + p95 latency / approximate cost per run.

---
**Lead every asset with:** the autonomous *trend → content → publish → measure →
adjust* loop, the human-approval gate, and MCP "bring your own tools" — with
Friday able to **write its own tools and MCP servers** at runtime.
