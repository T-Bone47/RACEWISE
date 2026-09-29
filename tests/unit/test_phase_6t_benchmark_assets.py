"""Phase 6T benchmark asset integrity tests.

Guards the Phase 6T corpus and runner contracts added by this phase: the
corpus must remain a valid structural benchmark (30+ autonomous questions
with the mandated category mix and limitation cases, no invented numeric
answers) and the runner must stay importable. These tests deliberately do
NOT execute the full chain (the runner is invoked manually and recorded in
docs, per the 6R convention).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "tests" / "benchmarks" / "phase_6t_autonomous_investigations.json"
RUNNER = ROOT / "tests" / "benchmarks" / "run_autonomous_benchmark.py"


def _load(path: Path) -> dict:
    assert path.exists(), f"missing 6T asset: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_corpus_exists_and_meets_phase_6t_minimums() -> None:
    data = _load(CORPUS)
    cases = data["cases"]
    ids = [c["benchmark_id"] for c in cases]
    assert len(cases) >= 30
    assert len(set(ids)) == len(ids)

    # mandated category mix
    by_kind: dict[str, int] = {}
    for c in cases:
        by_kind[c["category"]] = by_kind.get(c["category"], 0) + 1
    assert by_kind.get("lap", 0) >= 10
    assert by_kind.get("stint", 0) >= 5
    assert by_kind.get("qualifying", 0) >= 4
    assert by_kind.get("race_gap", 0) >= 4
    assert by_kind.get("regime", 0) >= 3
    assert by_kind.get("cross_race", 0) >= 2
    assert by_kind.get("counterfactual", 0) >= 2

    # mandated limitation coverage
    limitation_kinds = {c.get("limitation_case") for c in cases
                        if c.get("limitation_case")}
    for required in ("unknown_driver", "unsupported_question",
                     "budget_exhaustion", "missing_context",
                     "insufficient_evidence", "injection"):
        assert required in limitation_kinds, required


def test_corpus_questions_are_wellformed() -> None:
    data = _load(CORPUS)
    for c in data["cases"]:
        assert c["question"].strip(), c["benchmark_id"]
        assert c["category"], c["benchmark_id"]
        assert isinstance(c.get("expect", {}), dict)
        if c.get("context"):
            assert isinstance(c["context"], dict)


def test_runner_is_importable_and_offline_capable() -> None:
    import subprocess
    import sys
    r = subprocess.run(
        [sys.executable, str(RUNNER), "--help"],
        capture_output=True, text=True, timeout=120,
        cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[-400:]
    assert "--skip-api" in (r.stdout + r.stderr)
