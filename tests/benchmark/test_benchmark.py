"""Pytest wrapper so `pytest` exercises the benchmark path.

Runs the full benchmark through the API on the reference session and asserts
the honesty-critical properties: all tools complete, falsification attempted,
counterfactual executed. Scores are asserted on measured output, never fixed.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests" / "benchmark"))

from run_benchmark import BENCHMARK_QUESTIONS, run_benchmark


def test_benchmark_questions_complete_investigations():
    results = run_benchmark()
    assert len(results) == len(BENCHMARK_QUESTIONS)
    for r in results:
        assert r["state"] == "COMPLETED", f"{r['id']} did not complete: {r}"
        assert r["hypotheses"] >= 3
        assert r["tools_executed"] >= 3
        assert r["all_tools_completed"], f"{r['id']} had failed tool calls"
        assert r["falsification_attempted"], f"{r['id']} skipped falsification"
        assert r["counterfactual"], f"{r['id']} missing counterfactual"
