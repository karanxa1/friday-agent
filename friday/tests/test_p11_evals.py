"""P11 verification: reliability helpers + evals harness."""

from __future__ import annotations

import asyncio

import pytest

from core import reliability


def test_retry_succeeds_after_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("boom")
        return "ok"

    out = reliability.retry(flaky, attempts=5, base_delay=0.0, label="test")
    assert out == "ok" and calls["n"] == 3


def test_retry_reraises_after_exhausting():
    def always_fail():
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        reliability.retry(always_fail, attempts=2, base_delay=0.0)


def test_with_deadline_times_out():
    async def slow():
        await asyncio.sleep(2)

    with pytest.raises(TimeoutError):
        asyncio.run(reliability.with_deadline(slow(), seconds=0.1, label="slow"))


def test_eval_report_math():
    from evals.harness import EvalReport, RunResult

    rep = EvalReport(case="x", runs=4)
    rep.results = [
        RunResult(ok=True, latency_s=1.0, chars=100),
        RunResult(ok=True, latency_s=2.0, chars=200),
        RunResult(ok=False, latency_s=3.0, chars=0, error="e"),
        RunResult(ok=True, latency_s=4.0, chars=300),
    ]
    s = rep.summary()
    assert s["success_rate"] == 0.75
    assert s["avg_latency_s"] == 2.5
    assert "errors" in s


def test_eval_agent_case_runs_live():
    from evals.harness import run_eval

    report = asyncio.run(run_eval("agent", runs=1))
    assert report.runs == 1
    assert len(report.results) == 1
    # Should succeed against the local model.
    assert report.results[0].ok
