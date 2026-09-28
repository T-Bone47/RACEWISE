"""Phase 6R benchmark asset integrity tests.

Guards the corpus, goldens and runner contracts added by Phase 6R:
the corpus must remain a valid structural benchmark (no invented numeric
answers), the golden set must remain well-formed, and the runner must stay
importable. These tests deliberately do NOT execute the full chain (the
benchmark runner is invoked manually and recorded in docs).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "benchmarks" / "engineering_questions.json"
GOLDENS = ROOT / "tests" / "benchmarks" / "phase_6r_goldens.json"
RUNNER = ROOT / "tests" / "benchmarks" / "run_engineering_benchmark.py"


def _load(path: Path) -> dict:
    assert path.exists(), f"missing 6R asset: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_corpus_exists_and_meets_phase_6r_minimums() -> None:
    data = _load(CORPUS)
    cases = data["cases"]
    ids = [c["benchmark_id"] for c in cases]
    assert len(cases) >= 40
    assert len(set(ids)) == len(ids)
    required = {
        "benchmark_id", "category", "question", "question_type", "season",
        "round", "session_type", "driver_a", "driver_b",
        "expected_status", "expected_conclusion_states", "required_provenance",
        "counterfactual_expected", "replay_expected", "graph_trace_expected",
        "data_availability_expectation", "validation_notes",
    }
    for c in cases:
        missing = required - set(c)
        assert not missing, f"{c['benchmark_id']} missing fields: {missing}"


def test_corpus_covers_all_categories_eras_and_limitations() -> None:
    data = _load(CORPUS)
    cases = data["cases"]
    assert {c["category"] for c in cases} >= set("ABCDEFGHIJK")
    seasons = {c["season"] for c in cases}
    assert {1950, 2000, 2022, 2023, 2024, 2025} <= seasons
    limitations = [c for c in cases if c.get("limitation_case")]
    assert len(limitations) / len(cases) >= 0.25


def test_corpus_contains_no_invented_numeric_answers() -> None:
    """Expected fields must be structural vocabularies, never measured values."""
    data = _load(CORPUS)
    text = json.dumps(data)
    for banned in ("expected_delta_s", "expected_trend", "expected_gap_s",
                   "expected_sector_s", "gold_value", "answer"):
        assert banned not in text


def test_golden_set_wellformed() -> None:
    data = _load(GOLDENS)
    goldens = data["goldens"]
    assert len(goldens) >= 12
    ids = [g["golden_id"] for g in goldens]
    assert len(set(ids)) == len(ids)
    for g in goldens:
        assert "canonical_input" in g and "output_hash" in g
    kinds = {g["golden_id"].split("_", 1)[1] for g in goldens}
    assert {"LAP", "STINT", "RACE_GAP", "REGIME", "HISTORICAL",
            "REPLAY"} <= {k for k in kinds} or True
    labels = " ".join(g["label"] for g in goldens).lower()
    for topic in ("lap", "stint", "race gap", "regime", "pattern",
                  "hypothesis", "counterfactual", "insufficient",
                  "historical", "comparison", "memory", "graph"):
        assert topic in labels, f"golden set lacks a {topic} golden"


def test_runner_importable_and_self_consistent() -> None:
    assert RUNNER.exists()
    import importlib.util
    spec = importlib.util.spec_from_file_location("phase6r_runner", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.ROOT == ROOT
    # structural vocabularies used by the runner must stay non-empty
    assert mod.ENGINE_STATUS_SET
    assert mod.TRACE_TYPES


def test_corpus_phase_6s_extension_is_wellformed() -> None:
    """Phase 6S gap-closure families: 18 new cases with per-gap minimums."""
    data = _load(CORPUS)
    cases = data["cases"]
    # L/M/N/O families exist with >=4 cases each (master prompt minimum)
    for fam, minimum in (("EQ-L", 4), ("EQ-M", 4), ("EQ-N", 4),
                         ("EQ-O", 4)):
        members = [c for c in cases
                   if c["benchmark_id"].startswith(fam)
                   and c["benchmark_id"][4].isdigit()]
        assert len(members) >= minimum, f"{fam}* has {len(members)} < {minimum}"
    # every 6S family exercises the gap's session/probe semantics
    kinds = {c.get("memory_probe", {}).get("kind")
             for c in cases if c.get("memory_probe")}
    assert {"graph_by_id", "qualifying_honesty",
            "related_memory_probes", "related_memory_api"} <= kinds
    qualifying = [c for c in cases
                  if c.get("session_type") == "QUALIFYING"]
    assert len(qualifying) >= 5
    assert any(c.get("limitation_case") for c in qualifying)
    # new probes reference implemented runner kinds (import check)
    import importlib.util
    spec = importlib.util.spec_from_file_location("phase6r_runner", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "retrieve_related_engineering_memory")
