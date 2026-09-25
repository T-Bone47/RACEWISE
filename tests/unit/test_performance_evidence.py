"""Phase 6M tests: cross-race hypothesis & evidence intelligence.

Pure tests cover the 6G->6F state mapping, the documented aggregation rules
(including the contradiction regression: SUPPORTED+CONTRADICTED can never
become a consistent state), falsification aggregation, residual/sensitivity
summaries and evidence-vs-sensitivity alignment - all on synthetic data with
no DB. Tool/API/live tests run only when the canonical DB exists.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "canonical" / "canonical.db"
requires_db = pytest.mark.skipif(not DB_PATH.exists(), reason="canonical DB not present")

HIDS = ["H1_corner_speed", "H2_throttle", "H3_braking",
        "H4_tyre_state", "H5_race_control", "H6_drs"]


def _counts(supported=0, partial=0, not_supported=0, contradicted=0,
            not_testable=0, valid=None) -> dict:
    return {
        "valid_observations": (supported + partial + not_supported
                               + contradicted) if valid is None else valid,
        "supported_count": supported,
        "partially_supported_count": partial,
        "not_supported_count": not_supported,
        "contradicted_count": contradicted,
        "not_testable_count": not_testable,
    }


# ---------------------------------------------------------------------------
# 6G -> 6F mapping (pure)
# ---------------------------------------------------------------------------


class TestStateMapping:
    def test_consistent_and_mostly_map_to_supported(self):
        from racewise.data.historical.performance_evidence import (
            _map_hypothesis_state,
        )

        assert _map_hypothesis_state(
            "CONSISTENTLY_SUPPORTED", _counts(supported=3)) == "SUPPORTED"
        assert _map_hypothesis_state(
            "MOSTLY_SUPPORTED", _counts(supported=2, partial=1)) == "SUPPORTED"

    def test_intermittent_splits_on_contradiction(self):
        from racewise.data.historical.performance_evidence import (
            _map_hypothesis_state,
        )

        assert _map_hypothesis_state(
            "INTERMITTENTLY_SUPPORTED",
            _counts(supported=1, contradicted=1)) == "CONTRADICTED"
        assert _map_hypothesis_state(
            "INTERMITTENTLY_SUPPORTED",
            _counts(supported=1, partial=1)) == "PARTIALLY_SUPPORTED"

    def test_contradicted_over_time_and_not_supported(self):
        from racewise.data.historical.performance_evidence import (
            _map_hypothesis_state,
        )

        assert _map_hypothesis_state(
            "CONTRADICTED_OVER_TIME", _counts(not_supported=2)) == "NOT_SUPPORTED"
        assert _map_hypothesis_state(
            "NOT_SUPPORTED", _counts(not_supported=1)) == "NOT_SUPPORTED"

    def test_insufficient_summary_derives_from_counts(self):
        from racewise.data.historical.performance_evidence import (
            _map_hypothesis_state,
        )

        assert _map_hypothesis_state(
            "INSUFFICIENT_EVIDENCE", _counts()) == "INSUFFICIENT_EVIDENCE"
        assert _map_hypothesis_state(
            "INSUFFICIENT_EVIDENCE",
            _counts(supported=1, contradicted=1)) == "CONTRADICTED"
        assert _map_hypothesis_state(
            "INSUFFICIENT_EVIDENCE", _counts(supported=1)) == "PARTIALLY_SUPPORTED"
        assert _map_hypothesis_state(
            "INSUFFICIENT_EVIDENCE", _counts(not_supported=1)) == "NOT_SUPPORTED"

    def test_not_testable_passes_through(self):
        from racewise.data.historical.performance_evidence import (
            _map_hypothesis_state,
        )

        assert _map_hypothesis_state("NOT_TESTABLE", _counts()) == "NOT_TESTABLE"


# ---------------------------------------------------------------------------
# Aggregation rules + contradiction regression (pure, Section 29)
# ---------------------------------------------------------------------------


class TestAggregation:
    def _agg(self, *states: str) -> str:
        from racewise.data.historical.performance_evidence import (
            _aggregate_state,
        )

        return _aggregate_state(list(states))

    def test_case_a_all_supported(self):
        assert self._agg("SUPPORTED", "SUPPORTED") == "CONSISTENTLY_SUPPORTED"

    def test_case_b_majority_support_with_partial(self):
        assert self._agg("SUPPORTED", "PARTIALLY_SUPPORTED") == "MOSTLY_SUPPORTED"

    def test_case_c_supported_plus_not_supported_is_variable(self):
        assert self._agg("SUPPORTED", "NOT_SUPPORTED") == "VARIABLE"

    def test_case_d_contradiction_regression(self):
        # Section 29: SUPPORTED + CONTRADICTED must NEVER collapse into a
        # consistent state.
        agg = self._agg("SUPPORTED", "CONTRADICTED")
        assert agg == "CONTRADICTORY"
        assert agg not in ("CONSISTENTLY_SUPPORTED",
                           "CONSISTENTLY_NOT_SUPPORTED")

    def test_case_e_all_not_supported(self):
        assert self._agg("NOT_SUPPORTED", "NOT_SUPPORTED") == \
            "CONSISTENTLY_NOT_SUPPORTED"

    def test_case_f_no_informative_evidence(self):
        assert self._agg() == "INSUFFICIENT_EVIDENCE"
        assert self._agg("NOT_TESTABLE", "INSUFFICIENT_EVIDENCE") == \
            "INSUFFICIENT_EVIDENCE"

    def test_all_non_support_states_stay_consistent_not_supported(self):
        # CONTRADICTORY requires a support-class vs CONTRADICTED conflict
        # (Section 5 Case D); CONTRADICTED + NOT_SUPPORTED is all non-support
        # (Case E). The contradiction itself is still surfaced per-occurrence
        # via the profile's contradicting refs and falsification.
        assert self._agg("CONTRADICTED", "NOT_SUPPORTED") == \
            "CONSISTENTLY_NOT_SUPPORTED"
        assert self._agg("CONTRADICTED") == "CONSISTENTLY_NOT_SUPPORTED"

    def test_consistency_map(self):
        from racewise.data.historical.performance_evidence import (
            _CONSISTENCY_MAP,
        )

        assert _CONSISTENCY_MAP["CONTRADICTORY"] == "CONTRADICTORY"
        assert _CONSISTENCY_MAP["VARIABLE"] == "VARIABLE"
        assert _CONSISTENCY_MAP["MOSTLY_SUPPORTED"] == "VARIABLE"
        assert _CONSISTENCY_MAP["CONSISTENTLY_SUPPORTED"] == "CONSISTENT"
        assert _CONSISTENCY_MAP["INSUFFICIENT_EVIDENCE"] == "UNRESOLVED"


# ---------------------------------------------------------------------------
# Residual + sensitivity summaries (pure)
# ---------------------------------------------------------------------------


def _rows_from_means(means: list[float | None], states=None):
    """Synthetic rows/refs with race-ordered residual means."""
    from racewise.data.historical.performance_evidence import _finite

    refs, rows = [], []
    for i, m in enumerate(means):
        occ = {"season": 2023, "round": i + 1, "circuit_name": f"c{i}",
               "driver_pair": ["a", "b"], "regime_index": 1,
               "lap_range": "1-3", "pair_inverted_vs_canonical": False,
               "residual_state": (states or ["RESIDUAL_UNRESOLVED"] * len(means))[i],
               "residual_mean_s": m}
        refs.append({"season": 2023, "round": i + 1})
        rows.append({"idx": i, "occ": occ, "cells": {}})
    return rows, refs


class TestResidualSummary:
    def test_stable_when_same_sign_small_spread(self):
        from racewise.data.historical.performance_evidence import (
            _residual_summary,
        )

        rows, refs = _rows_from_means([0.10, 0.11, 0.12])
        out = _residual_summary(rows, refs)
        assert out["residual_pattern"] == "RESIDUAL_STABLE"
        assert out["residual_mean_range_s"] == pytest.approx(0.02, abs=1e-9)

    def test_increasing_and_decreasing(self):
        from racewise.data.historical.performance_evidence import (
            _residual_summary,
        )

        rows, refs = _rows_from_means([0.05, 0.10, 0.20, 0.35])
        assert _residual_summary(rows, refs)["residual_pattern"] == \
            "RESIDUAL_INCREASING"
        rows, refs = _rows_from_means([0.35, 0.20, 0.10, 0.05])
        assert _residual_summary(rows, refs)["residual_pattern"] == \
            "RESIDUAL_DECREASING"

    def test_reversal_on_sign_change_with_spread(self):
        from racewise.data.historical.performance_evidence import (
            _residual_summary,
        )

        # V-shaped series: zero OLS slope, mixed signs, spread > 0.10 s
        rows, refs = _rows_from_means([0.15, -0.15, 0.15])
        assert _residual_summary(rows, refs)["residual_pattern"] == \
            "RESIDUAL_REVERSAL"

    def test_unresolved_when_no_measured_residuals(self):
        from racewise.data.historical.performance_evidence import (
            _residual_summary,
        )

        rows, refs = _rows_from_means([None, None])
        assert _residual_summary(rows, refs)["residual_pattern"] == \
            "INSUFFICIENT_EVIDENCE"

    def test_residuals_never_assigned(self):
        from racewise.data.historical.performance_evidence import (
            _residual_summary,
        )

        rows, refs = _rows_from_means([0.1, 0.2, 0.3])
        out = _residual_summary(rows, refs)
        assert "never assigned" in out["note"]


class TestSensitivitySummary:
    def _rows(self, statuses, deltas):
        refs, rows = [], []
        for i, (st, d) in enumerate(zip(statuses, deltas)):
            occ = {"season": 2023, "round": i + 1, "circuit_name": f"c{i}",
                   "driver_pair": ["a", "b"], "regime_index": 1,
                   "lap_range": "1-3", "pair_inverted_vs_canonical": False,
                   "telemetry_status": st,
                   "sensitivity_status": "VALID" if d is not None else st,
                   "sensitivity_delta_s": d, "sensitivity_parameter": 0.5}
            refs.append({"season": 2023, "round": i + 1})
            rows.append({"idx": i, "occ": occ, "cells": {}})
        return rows, refs

    def test_no_telemetry_is_unavailable_not_zero(self):
        from racewise.data.historical.performance_evidence import (
            _sensitivity_summary,
        )

        rows, refs = self._rows(["TELEMETRY_UNAVAILABLE"] * 2, [None, None])
        out = _sensitivity_summary(rows, refs)
        assert out["status"] == "TELEMETRY_UNAVAILABLE"

    def test_single_value_is_insufficient(self):
        from racewise.data.historical.performance_evidence import (
            _sensitivity_summary,
        )

        rows, refs = self._rows(["TELEMETRY_AVAILABLE"] * 2, [-1.0, None])
        assert _sensitivity_summary(rows, refs)["status"] == \
            "INSUFFICIENT_EVIDENCE"

    def test_two_values_are_valid_with_spread(self):
        from racewise.data.historical.performance_evidence import (
            _sensitivity_summary,
        )

        rows, refs = self._rows(["TELEMETRY_AVAILABLE"] * 2, [-1.0, -2.0])
        out = _sensitivity_summary(rows, refs)
        assert out["status"] == "VALID"
        assert out["spread_s"] == pytest.approx(1.0, abs=1e-9)
        assert out["telemetry_supported_occurrences"] == 2

    def test_interpretation_bound_present(self):
        from racewise.data.historical.performance_evidence import (
            _sensitivity_summary,
        )

        rows, refs = self._rows(["TELEMETRY_AVAILABLE"] * 2, [-1.0, -2.0])
        out = _sensitivity_summary(rows, refs)
        assert "not a historical effect" in out["interpretation_bound"]


class TestEvidenceVsSensitivity:
    def test_consistent_evidence_aligned_model(self):
        from racewise.data.historical.performance_evidence import (
            _evidence_vs_sensitivity,
        )

        profiles = [{"hypothesis_id": "H1_corner_speed",
                     "aggregate_state": "CONSISTENTLY_SUPPORTED"}]
        sens = {"status": "VALID", "spread_s": 0.2}
        out = _evidence_vs_sensitivity(profiles, sens)
        assert out["per_hypothesis"]["H1_corner_speed"]["interpretation"] == \
            "CONSISTENT_EVIDENCE_AND_MODEL_RESPONSE"

    def test_variable_evidence(self):
        from racewise.data.historical.performance_evidence import (
            _evidence_vs_sensitivity,
        )

        profiles = [{"hypothesis_id": "H1_corner_speed",
                     "aggregate_state": "VARIABLE"}]
        out = _evidence_vs_sensitivity(
            profiles, {"status": "VALID", "spread_s": 0.2})
        assert out["per_hypothesis"]["H1_corner_speed"]["interpretation"] == \
            "VARIABLE_EVIDENCE_AND_MODEL_RESPONSE"

    def test_evidence_only_when_sensitivity_unavailable(self):
        from racewise.data.historical.performance_evidence import (
            _evidence_vs_sensitivity,
        )

        profiles = [{"hypothesis_id": "H1_corner_speed",
                     "aggregate_state": "CONSISTENTLY_SUPPORTED"}]
        out = _evidence_vs_sensitivity(
            profiles, {"status": "TELEMETRY_UNAVAILABLE"})
        assert out["per_hypothesis"]["H1_corner_speed"]["interpretation"] == \
            "EVIDENCE_ONLY"

    def test_both_unavailable(self):
        from racewise.data.historical.performance_evidence import (
            _evidence_vs_sensitivity,
        )

        profiles = [{"hypothesis_id": "H1_corner_speed",
                     "aggregate_state": "INSUFFICIENT_EVIDENCE"}]
        out = _evidence_vs_sensitivity(
            profiles, {"status": "TELEMETRY_UNAVAILABLE"})
        assert out["per_hypothesis"]["H1_corner_speed"]["interpretation"] == \
            "BOTH_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Profiles, matrix, falsification, cross-race check (pure)
# ---------------------------------------------------------------------------


def _occ_row(idx: int, counts_by_hyp: dict[str, dict],
             summaries: dict[str, str] | None = None) -> dict:
    from racewise.data.historical.performance_evidence import _occurrence_cell

    occ = {
        "season": 2023, "round": idx + 1, "circuit_name": f"c{idx}",
        "driver_pair": ["a", "b"], "regime_index": idx,
        "lap_range": "1-3", "pair_inverted_vs_canonical": False,
        "residual_state": "RESIDUAL_UNRESOLVED", "residual_mean_s": None,
        "telemetry_status": "TELEMETRY_UNAVAILABLE",
        "sensitivity_status": "UNAVAILABLE", "sensitivity_delta_s": None,
        "sensitivity_parameter": None,
        "hypothesis_counts": {h: counts_by_hyp.get(h, _counts())
                              for h in HIDS},
        "hypothesis_state_summary": summaries or {},
        "compound_summary": ["MEDIUM"], "pit_overlap": False,
        "race_control_overlap": False,
    }
    return {"idx": idx, "occ": occ, "cells": _occurrence_cell(occ)}


def _refs_for(n: int, pattern_id: str = "p0"):
    from racewise.data.historical.performance_evidence import _occurrence_ref

    occs = [{"season": 2023, "round": i + 1, "circuit_name": f"c{i}",
             "driver_pair": ["a", "b"], "regime_index": i,
             "lap_range": "1-3", "pair_inverted_vs_canonical": False}
            for i in range(n)]
    return [_occurrence_ref(o, pattern_id) for o in occs]


class TestProfilesAndMatrix:
    def _run(self, cells_per_row: list[dict[str, dict]],
             summaries_per_row: list[dict[str, str]] | None = None):
        from racewise.data.historical.performance_evidence import (
            _evidence_matrix, _hypothesis_profile,
        )

        n = len(cells_per_row)
        summaries_per_row = summaries_per_row or [{} for _ in range(n)]
        rows = [_occ_row(i, cells, summaries)
                for i, (cells, summaries) in
                enumerate(zip(cells_per_row, summaries_per_row))]
        refs = _refs_for(len(rows))
        profiles = [_hypothesis_profile(h, rows, refs) for h in HIDS]
        matrix = _evidence_matrix(rows, refs)
        return rows, refs, profiles, matrix

    def test_matrix_preserves_underlying_states(self):
        cells = {"H1_corner_speed": _counts(supported=2)}
        summaries = {h: "CONSISTENTLY_SUPPORTED" for h in HIDS}
        _, _, _, matrix = self._run([cells, cells, cells],
                                    [summaries] * 3)
        assert matrix["columns"] == HIDS
        assert len(matrix["rows"]) == 3
        cell = matrix["rows"][0]["cells"]["H1_corner_speed"]
        assert cell["mapped_state"] == "SUPPORTED"
        assert cell["underlying_counts"]["supported_count"] == 2

    def test_contradiction_preserved_in_profile(self):
        sup = {"H1_corner_speed": _counts(supported=2)}
        con = {"H1_corner_speed": _counts(supported=1, contradicted=1)}
        _, _, profiles, _ = self._run(
            [sup, con],
            [{"H1_corner_speed": "CONSISTENTLY_SUPPORTED"},
             {"H1_corner_speed": "INTERMITTENTLY_SUPPORTED"}])
        h1 = next(p for p in profiles if p["hypothesis_id"] == "H1_corner_speed")
        assert h1["aggregate_state"] == "CONTRADICTORY"
        assert len(h1["supporting_occurrences"]) == 1
        assert len(h1["contradicting_occurrences"]) == 1
        assert h1["falsification_status"] == "FALSIFICATION_PRESENT"

    def test_no_falsification_is_not_confirmation(self):
        sup = {"H2_throttle": _counts(supported=2)}
        _, _, profiles, _ = self._run([sup, sup])
        h2 = next(p for p in profiles if p["hypothesis_id"] == "H2_throttle")
        assert h2["falsification_status"] == "NO_FALSIFICATION_FOUND"
        assert "not confirmation" in h2["falsification_note"]

    def test_coverage_counts_are_explicit_not_confidence(self):
        sup = {"H3_braking": _counts(supported=2)}
        _, _, profiles, _ = self._run(
            [sup, {}, {}],
            [{"H3_braking": "CONSISTENTLY_SUPPORTED"}, {}, {}])
        h3 = next(p for p in profiles if p["hypothesis_id"] == "H3_braking")
        cov = h3["evidence_coverage"]
        assert cov["informative_occurrences"] == 1
        assert cov["insufficient_occurrences"] == 2
        # the single informative occurrence is SUPPORTED -> Case A over the
        # informative set (coverage is reported explicitly, never as confidence)
        assert h3["aggregate_state"] == "CONSISTENTLY_SUPPORTED"


class TestCrossRaceCheck:
    def _check(self, aggregates: list[str]) -> str:
        from racewise.data.historical.performance_evidence import (
            _cross_race_falsification_check,
        )

        profiles = [{"aggregate_state": a} for a in aggregates]
        return _cross_race_falsification_check(profiles)["result"]

    def test_consistent_support(self):
        assert self._check(["CONSISTENTLY_SUPPORTED",
                            "CONSISTENTLY_SUPPORTED"]) == "CONSISTENT_SUPPORT"

    def test_contradicted_by_occurrence(self):
        assert self._check(["CONSISTENTLY_SUPPORTED",
                            "CONTRADICTORY"]) == "CONTRADICTED_BY_OCCURRENCE"

    def test_mixed_support(self):
        assert self._check(["CONSISTENTLY_SUPPORTED",
                            "CONSISTENTLY_NOT_SUPPORTED"]) == "MIXED_SUPPORT"

    def test_not_testable_and_insufficient(self):
        assert self._check(["INSUFFICIENT_EVIDENCE",
                            "INSUFFICIENT_EVIDENCE"]) == "INSUFFICIENT_EVIDENCE"


class TestInputValidation:
    def test_same_driver_invalid_before_any_scan(self):
        from racewise.data.historical.performance_evidence import (
            analyze_cross_race_pattern_evidence,
        )

        out = analyze_cross_race_pattern_evidence(
            None, "max-verstappen", "max-verstappen", "p")
        assert out["status"] == "INVALID"

    def test_bound_violation_invalid_before_any_scan(self):
        from racewise.data.historical.performance_evidence import (
            MAX_OCCURRENCES, analyze_cross_race_pattern_evidence,
        )

        out = analyze_cross_race_pattern_evidence(
            None, "a", "b", "p", max_occurrences=MAX_OCCURRENCES + 1)
        assert out["status"] == "INVALID"
        out = analyze_cross_race_pattern_evidence(None, "a", "b", "p",
                                                  max_occurrences=0)
        assert out["status"] == "INVALID"

    def test_non_recurring_pattern_is_insufficient(self, monkeypatch):
        # 6L only reports RECURRING patterns, so this branch is defensive;
        # it must still return the explicit state rather than fabricate.
        import racewise.data.historical.performance_evidence as ev

        def fake_patterns(*_a, **_k):
            return {"status": "VALID", "pattern_count": 1,
                    "patterns": [{"pattern_id": "p1",
                                  "pattern_version": "v1",
                                  "recurrence_classification": "NON_RECURRING",
                                  "occurrences": [], "provenance": {}}]}

        monkeypatch.setattr(ev, "analyze_cross_race_performance_patterns",
                            fake_patterns)
        out = ev.analyze_cross_race_pattern_evidence(None, "a", "b", "p1",
                                                     max_occurrences=4)
        assert out["status"] == "INSUFFICIENT_EVIDENCE"


# ---------------------------------------------------------------------------
# Live corpus tests (canonical DB required)
# ---------------------------------------------------------------------------


@requires_db
class TestLiveCorpus:
    PAIR = ("max-verstappen", "sergio-perez")
    SEASONS = [2022, 2023]

    def _investigate(self, pattern_id: str, max_occurrences: int = 6):
        from racewise.data.historical.canonical_queries import (
            get_canonical_queries,
        )
        from racewise.data.historical.performance_evidence import (
            analyze_cross_race_pattern_evidence,
        )

        return analyze_cross_race_pattern_evidence(
            get_canonical_queries(), self.PAIR[0], self.PAIR[1],
            pattern_id, seasons=self.SEASONS,
            max_occurrences=max_occurrences)

    def _most_contradictory_pattern(self) -> str:
        from racewise.data.historical.canonical_queries import (
            get_canonical_queries,
        )
        from racewise.data.historical.performance_patterns import (
            analyze_cross_race_performance_patterns,
        )
        from racewise.data.historical.q15_benchmarks import _pick_patterns

        pat = analyze_cross_race_performance_patterns(
            get_canonical_queries(), self.PAIR[0], self.PAIR[1],
            seasons=self.SEASONS, max_races=8, max_patterns=20)
        assert pat["status"] == "VALID"
        return _pick_patterns(pat["patterns"])["most_contradictory"]

    def test_valid_investigation_contract(self):
        pid = self._most_contradictory_pattern()
        inv = self._investigate(pid)
        assert inv["status"] == "VALID"
        assert inv["pattern_id"] == pid
        assert inv["independent_race_count"] >= 2
        assert len(inv["hypothesis_profiles"]) == 6
        assert inv["evidence_matrix"]["columns"] == HIDS
        assert len(inv["evidence_matrix"]["rows"]) == inv["occurrence_count"]
        assert inv["provenance"]["analytical_chain"] == [
            "6E", "6F", "6G", "6H", "6I", "6J", "6K", "6L", "6M"]
        assert inv["provenance"]["generated_at"] is None
        assert inv["epistemic_boundaries"]
        assert inv["sensitivity_summary"]["status"] in (
            "VALID", "INSUFFICIENT_EVIDENCE", "TELEMETRY_UNAVAILABLE")
        assert inv["residual_summary"]["residual_pattern"] in (
            "RESIDUAL_STABLE", "RESIDUAL_INCREASING", "RESIDUAL_DECREASING",
            "RESIDUAL_REVERSAL", "RESIDUAL_UNRESOLVED",
            "INSUFFICIENT_EVIDENCE")

    def test_missing_pattern_is_unavailable(self):
        inv = self._investigate("0000000000000000")
        assert inv["status"] == "UNAVAILABLE"

    def test_unavailable_scope_propagates_with_phase_status(self):
        # 1950 has no telemetry-capable sessions: 6L returns UNAVAILABLE on
        # its fast path and 6M propagates it explicitly.
        from racewise.data.historical.canonical_queries import (
            get_canonical_queries,
        )
        from racewise.data.historical.performance_evidence import (
            analyze_cross_race_pattern_evidence,
        )

        inv = analyze_cross_race_pattern_evidence(
            get_canonical_queries(), self.PAIR[0], self.PAIR[1], "any",
            seasons=[1950], max_occurrences=4)
        assert inv["status"] == "UNAVAILABLE"
        assert inv["phase_6l_status"] == "UNAVAILABLE"

    def test_contradiction_regression_live(self):
        pid = self._most_contradictory_pattern()
        inv = self._investigate(pid)
        assert inv["status"] == "VALID"
        contradicted = inv["contradiction_summary"][
            "hypotheses_with_contradictions"]
        if not contradicted:
            pytest.skip("corpus carries no contradictory pattern today")
        for p in inv["hypothesis_profiles"]:
            if p["hypothesis_id"] in contradicted:
                assert p["aggregate_state"] == "CONTRADICTORY"
                assert p["contradicting_occurrences"]
                # cells preserve the underlying contradiction counts
                ref = p["contradicting_occurrences"][0]
                row = next(r for r in inv["evidence_matrix"]["rows"]
                           if r["ref"]["season"] == ref["season"]
                           and r["ref"]["round"] == ref["round"]
                           and r["ref"]["regime_index"] == ref["regime_index"])
                cell = row["cells"][p["hypothesis_id"]]
                assert cell["underlying_counts"]["contradicted_count"] > 0

    def test_determinism_subprocess_and_hashseed(self):
        pid = self._most_contradictory_pattern()
        code = (
            "import sys, json; sys.path.insert(0, r'%s');\n"
            "from racewise.data.historical.canonical_queries import "
            "get_canonical_queries\n"
            "from racewise.data.historical.performance_evidence import "
            "analyze_cross_race_pattern_evidence\n"
            "inv = analyze_cross_race_pattern_evidence(\n"
            "    get_canonical_queries(), '%s', '%s', '%s',\n"
            "    seasons=%r, max_occurrences=4)\n"
            "print(json.dumps([inv['status'], inv.get('output_hash')]))\n"
            % (REPO / "src", self.PAIR[0], self.PAIR[1], pid, self.SEASONS)
        )
        env1 = {**os.environ, "PYTHONHASHSEED": "3"}
        env2 = {**os.environ, "PYTHONHASHSEED": "29"}
        r1 = subprocess.run([sys.executable, "-c", code], capture_output=True,
                            text=True, env=env1, timeout=560)
        r2 = subprocess.run([sys.executable, "-c", code], capture_output=True,
                            text=True, env=env2, timeout=560)
        assert r1.returncode == 0 and r2.returncode == 0, r1.stderr + r2.stderr
        assert r1.stdout.strip() == r2.stdout.strip()
        assert json.loads(r1.stdout)[0] == "VALID"

    def test_registry_boundary(self):
        from racewise.tools.contract import ToolError
        from racewise.data.historical.canonical_queries import (
            get_canonical_queries,
        )
        from racewise.tools.historical import build_historical_registry

        reg = build_historical_registry(get_canonical_queries())
        name = "analyze_cross_race_pattern_evidence"
        assert name in reg.names()
        for label, kw in (
            ("same-driver", {"driver_a": self.PAIR[0],
                             "driver_b": self.PAIR[0], "pattern_id": "x"}),
            ("bound", {"driver_a": self.PAIR[0], "driver_b": self.PAIR[1],
                       "pattern_id": "x", "max_occurrences": 9}),
            ("unknown-param", {"driver_a": self.PAIR[0],
                               "driver_b": self.PAIR[1], "pattern_id": "x",
                               "zzz": 1}),
            ("empty-pattern-id", {"driver_a": self.PAIR[0],
                                  "driver_b": self.PAIR[1],
                                  "pattern_id": "  "}),
        ):
            with pytest.raises(ToolError):
                reg.execute(name, kw)

    def test_api_endpoint(self):
        from fastapi.testclient import TestClient

        from racewise.api.app import app

        client = TestClient(app)
        pid = self._most_contradictory_pattern()
        params = {"driver_a": self.PAIR[0], "driver_b": self.PAIR[1],
                  "pattern_id": pid, "seasons": "2022,2023",
                  "max_occurrences": 4}
        r1 = client.get("/api/catalog/performance-pattern-evidence",
                        params=params)
        assert r1.status_code == 200
        assert r1.json()["status"] == "VALID"
        r2 = client.get("/api/catalog/performance-pattern-evidence",
                        params=params)
        assert r1.content == r2.content
        assert client.get(
            "/api/catalog/performance-pattern-evidence").status_code == 422
        bad = {**params, "max_occurrences": 99}
        assert client.get("/api/catalog/performance-pattern-evidence",
                          params=bad).status_code == 422
