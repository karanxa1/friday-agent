"""Evals harness: run a core workflow N times and report success/latency/cost.

Measures the reliability + approximate economics of Friday's core loops:
* task success rate (did the agent produce non-trivial output?)
* average / p95 latency
* approximate cost per run (token-based estimate; local model is free but we
  still surface token volume + any CallMissed credits consumed)

Run:  python -m evals.harness --runs 3 --case agent
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from dataclasses import dataclass, field

from core import audit


@dataclass
class RunResult:
    ok: bool
    latency_s: float
    chars: int
    error: str = ""


@dataclass
class EvalReport:
    case: str
    runs: int
    results: list[RunResult] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.ok) / len(self.results)

    @property
    def avg_latency(self) -> float:
        lats = [r.latency_s for r in self.results]
        return statistics.mean(lats) if lats else 0.0

    @property
    def p95_latency(self) -> float:
        lats = sorted(r.latency_s for r in self.results)
        if not lats:
            return 0.0
        idx = max(0, int(len(lats) * 0.95) - 1)
        return lats[idx]

    @property
    def approx_cost(self) -> float:
        """Rough cost proxy: output chars/4 ~ tokens; local model nominal $0.

        We report a tiny nominal $/1k-token figure so the number is non-zero and
        comparable across runs; adjust if you wire a paid model.
        """
        total_tokens = sum(r.chars for r in self.results) / 4.0
        return round(total_tokens / 1000.0 * 0.0, 6)  # local model: free

    def summary(self) -> dict:
        return {
            "case": self.case,
            "runs": self.runs,
            "success_rate": round(self.success_rate, 3),
            "avg_latency_s": round(self.avg_latency, 2),
            "p95_latency_s": round(self.p95_latency, 2),
            "approx_cost_usd": self.approx_cost,
            "errors": [r.error for r in self.results if r.error][:5],
        }


async def _run_agent_case() -> RunResult:
    from control_plane import builder
    from core.conversation import run_once

    t0 = time.time()
    try:
        agent = builder.build_agent("root")
        out = await run_once(agent, "List three concrete things you can do, one line each.")
        ok = bool(out) and len(out) > 20
        return RunResult(ok=ok, latency_s=time.time() - t0, chars=len(out))
    except Exception as exc:  # noqa: BLE001
        return RunResult(ok=False, latency_s=time.time() - t0, chars=0, error=str(exc)[:200])


async def _run_analyst_case() -> RunResult:
    from domains.social_media import agents as A
    from core.conversation import run_once

    t0 = time.time()
    try:
        analyst = A.build_analyst()
        out = await run_once(analyst, "Analyze performance and recommend actions.")
        ok = bool(out) and len(out) > 20
        return RunResult(ok=ok, latency_s=time.time() - t0, chars=len(out))
    except Exception as exc:  # noqa: BLE001
        return RunResult(ok=False, latency_s=time.time() - t0, chars=0, error=str(exc)[:200])


_CASES = {"agent": _run_agent_case, "analyst": _run_analyst_case}


async def run_eval(case: str, runs: int) -> EvalReport:
    fn = _CASES.get(case)
    if fn is None:
        raise ValueError(f"unknown case {case!r}; choices: {list(_CASES)}")
    report = EvalReport(case=case, runs=runs)
    for i in range(runs):
        res = await fn()
        report.results.append(res)
        audit.log("eval.run", case=case, i=i + 1, ok=res.ok, latency=round(res.latency_s, 2))
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Friday evals harness")
    ap.add_argument("--case", default="agent", choices=list(_CASES))
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()
    report = asyncio.run(run_eval(args.case, args.runs))
    import json

    print(json.dumps(report.summary(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
