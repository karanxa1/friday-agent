"""Friday CLI entrypoint.

Usage:
  python -m cli serve [--host 0.0.0.0] [--port 8080]   # run the dashboard + API
  python -m cli run "your goal"                         # one-shot agent run
  python -m cli social --niche "developer tools"        # run the social loop
  python -m cli eval --case agent --runs 3              # run the evals harness
  python -m cli curator                                 # run the curator once
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys


def _serve(args) -> int:
    import uvicorn

    uvicorn.run("control_plane.app:app", host=args.host, port=args.port, log_level="info")
    return 0


def _run(args) -> int:
    from control_plane import builder
    from core.conversation import run_once

    agent = builder.build_agent("root")
    out = asyncio.run(run_once(agent, args.goal))
    print(out)
    return 0


def _social(args) -> int:
    from domains.social_media.loop import run_social_loop

    res = asyncio.run(run_social_loop(args.goal, args.niche, args.brand))
    print("=== TRENDS ===\n", res["trends"][:600])
    print("\n=== ANALYSIS ===\n", res["analysis"][:600])
    print("\n=== PENDING APPROVALS:", len(res["pending_approvals"]))
    for p in res["pending_approvals"]:
        print(f"  [{p['type']}] {p['summary']}")
    return 0


def _eval(args) -> int:
    from evals.harness import run_eval

    report = asyncio.run(run_eval(args.case, args.runs))
    print(json.dumps(report.summary(), indent=2))
    return 0


def _curator(args) -> int:
    from curator.curator import run

    print(json.dumps(run(force=True), indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="friday", description="Friday autonomous agent CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="run the dashboard + API")
    # Bind localhost by default; the control plane is unauthenticated unless
    # FRIDAY_API_TOKEN is set. Use --host 0.0.0.0 only behind an auth layer.
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8080)
    s.set_defaults(fn=_serve)

    r = sub.add_parser("run", help="one-shot agent run")
    r.add_argument("goal")
    r.set_defaults(fn=_run)

    so = sub.add_parser("social", help="run the social-media loop")
    so.add_argument("--goal", default="grow launch awareness this week")
    so.add_argument("--niche", default="developer tools")
    so.add_argument("--brand", default=None)
    so.set_defaults(fn=_social)

    e = sub.add_parser("eval", help="run the evals harness")
    e.add_argument("--case", default="agent")
    e.add_argument("--runs", type=int, default=3)
    e.set_defaults(fn=_eval)

    c = sub.add_parser("curator", help="run the skill curator once")
    c.set_defaults(fn=_curator)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
