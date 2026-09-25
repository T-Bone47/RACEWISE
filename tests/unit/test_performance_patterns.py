"""Phase 6L tests: cross-race performance pattern intelligence.

Pure tests cover signature construction/normalization, the comparability
contract, component-distance matching, recurrence/aggregation helpers and
hashing with synthetic data (no DB). Tool/API/live tests run only when the
canonical DB exists and validate real data through the registry, API and
Q14-style bounded matrices.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "canonical" / "canonical.db"
requires_db = pytest.mark.skipif(not DB_PATH.exists(), reason="canonical DB not present")


# ---------------------------------------------------------------------------
# pure helpers (synthetic data, no DB)
# ---------------------------------------------------------------------------


class TestPureHelpers:
    def test_canon_pair_order_independent(self):
        from racewise.data.historical.performance_patterns import _canon_pair

        assert _canon_pair("b", "a") == _canon_pair("a", "b") == ("a", "b")

    def test_hash_obj_is_json_deterministic(self):
        from racewise.data.historical.performance_patterns import _hash_obj

        obj = {"b": 1, "a": [1.5, None, "x"]}
        assert _hash_obj(obj) == _hash_obj({"a": [1.5, None, "x"], "b": 1})

    def test_hash_obj_independent_of_pythonhashseed(self):
        import os
        from racewise.data.historical.performance_patterns import _hash_obj

        code = (
            "import sys; sys.path.insert(0, r'%s');\n"
            "from racewise.data.historical.performance_patterns import _hash_obj\n"
            "print(_hash_obj({'k': ['a', 'b'], 'slope_state': 'NEGATIVE'}))"
            % (REPO / "src",)
        )
        env1 = {**os.environ, "PYTHONHASHSEED": "1"}
        env2 = {**os.environ, "PYTHONHASHSEED": "42"}
        r1 = subprocess.run([sys.executable, "-c", code], capture_output=True,
                            text=True, env=env1, timeout=120)
        r2 = subprocess.run([sys.executable, "-c", code], capture_output=True,
                            text=True, env=env2, timeout=120)
        assert r1.returncode == 0 and r2.returncode == 0, r1.stderr
        assert r1.stdout.strip() == r2.stdout.strip()

    def test_duration_bucket(self):
        from racewise.data.historical.performance_patterns import _duration_bucket

        assert _duration_bucket(3) == "2-3"
        assert _duration_bucket(4) == "4-6"
        assert _duration_bucket(9) == "7-10"
        assert _duration_bucket(14) == "11+"

    def test_normalized_shape_resamples_inside_measured_span(self):
        from racewise.data.historical.performance_patterns import _normalized_shape

        shape = _normalized_shape([[10, 0.0], [11, 1.0], [12, 2.0], [13, 3.0]])
        assert shape is not None and len(shape) == 8
        # endpoints clamp to measured values; middle interpolates
        assert shape[0] == 0.0 and shape[-1] == 3.0
        assert shape[4] == pytest.approx(12 / 7, abs=1e-3)

    def test_normalized_shape_needs_two_points(self):
        from racewise.data.historical.performance_patterns import _normalized_shape

        assert _normalized_shape([[10, 0.5]]) is None
        assert _normalized_shape([]) is None


class TestSignature:
    def _regime(self) -> dict:
        return {
            "regime_index": 2, "start_lap": 5, "end_lap": 8, "lap_count": 4,
            "slope_s_per_lap": 0.1234, "pattern": "WIDENING",
            "telemetry_state": "AVAILABLE", "telemetry_lap_count": 4,
            "stints_spanned": [1],
            "context": {"compounds": ["MEDIUM"], "pit_laps": [],
                        "restricted_laps": []},
            "delta_series": [[5, 0.5], [6, 0.6], [7, 0.9], [8, 1.0]],
            "hypothesis_evolution": [
                {"hypothesis_id": "H1_corner_speed", "summary": "SUPPORTED"},
            ],
            "residual": {"laps_fused": 4, "residual_total_s": -0.4,
                         "state": "PRESERVED"},
            "model_sensitivity": {"status": "VALID", "delta_s": -1.5,
                                  "fraction": 0.5,
                                  "band_width_mean_kmh": 20.0},
        }

    def _race(self) -> dict:
        return {"season": 2023, "round": 1, "race_id": "racex",
                "circuit_name": "test-circuit"}

    def test_signature_fields_measured_only(self):
        from racewise.data.historical.performance_patterns import _regime_signature

        sig = _regime_signature(self._race(), self._regime(),
                                "driver-a", "driver-b", "hash0")
        assert sig["race_identity"]["season"] == 2023
        assert sig["trend_classification"] == "WIDENING"
        assert sig["slope_s_per_lap"] == 0.1234
        assert sig["residual_state"] == "RESIDUAL_UNRESOLVED"  # PRESERVED mapped
        assert sig["residual_mean_s"] == pytest.approx(-0.1, abs=1e-9)
        assert sig["model_sensitivity"]["delta_s"] == -1.5
        assert sig["envelope_width_mean_kmh"] == 20.0
        assert sig["normalized_shape"] is not None
        assert sig["provenance"]["regime_output_hash"] == "hash0"
        assert sig["hypothesis_state_summary"] == {"H1_corner_speed": "SUPPORTED"}

    def test_signature_inversion_negates_signed_quantities(self):
        from racewise.data.historical.performance_patterns import _regime_signature

        sig = _regime_signature(self._race(), self._regime(),
                                "driver-b", "driver-a", "hash0")
        assert sig["pair_inverted_vs_canonical"] is True
        assert sig["canonical_pair"] == ["driver-a", "driver-b"]
        assert sig["slope_s_per_lap"] == -0.1234
        assert sig["residual_mean_s"] == pytest.approx(0.1, abs=1e-9)
        assert sig["model_sensitivity"]["delta_s"] == 1.5
        assert sig["delta_series"] == [[5, -0.5], [6, -0.6], [7, -0.9], [8, -1.0]]

    def test_structural_key_excludes_race_identity_and_floats(self):
        from racewise.data.historical.performance_patterns import (
            _hash_obj,
            _regime_signature,
            _structural_key,
        )

        s1 = _structural_key(_regime_signature(self._race(), self._regime(),
                                               "driver-a", "driver-b", "h1"))
        race2 = {**self._race(), "season": 2024, "round": 9,
                 "race_id": "other", "circuit_name": "elsewhere"}
        regime2 = {**self._regime(), "start_lap": 30, "end_lap": 33}
        s2 = _structural_key(_regime_signature(race2, regime2,
                                               "driver-a", "driver-b", "h2"))
        assert _hash_obj(s1) == _hash_obj(s2)

    def test_structural_key_distinguishes_trend_and_telemetry(self):
        from racewise.data.historical.performance_patterns import (
            _hash_obj,
            _regime_signature,
            _structural_key,
        )

        base = _structural_key(_regime_signature(
            self._race(), self._regime(), "driver-a", "driver-b", "h"))
        alt_regime = {**self._regime(), "pattern": "NARROWING",
                      "slope_s_per_lap": -0.4}
        alt = _structural_key(_regime_signature(
            self._race(), alt_regime, "driver-a", "driver-b", "h"))
        assert _hash_obj(base) != _hash_obj(alt)


class TestMatching:
    def _sig(self, **over) -> dict:
        from racewise.data.historical.performance_patterns import _regime_signature

        regime = {
            "regime_index": 1, "start_lap": 5, "end_lap": 9, "lap_count": 5,
            "slope_s_per_lap": 0.12, "pattern": "WIDENING",
            "telemetry_state": "AVAILABLE", "telemetry_lap_count": 5,
            "stints_spanned": [1],
            "context": {"compounds": ["MEDIUM"], "pit_laps": [],
                        "restricted_laps": []},
            "delta_series": [[5, 0.5], [6, 0.6], [7, 0.7], [8, 0.8], [9, 0.9]],
            "hypothesis_evolution": [
                {"hypothesis_id": "H1_corner_speed", "summary": "NOT_TESTABLE"},
            ],
            "residual": {"laps_fused": 5, "residual_total_s": 0.5,
                         "state": "PRESERVED"},
            "model_sensitivity": {"status": "VALID", "delta_s": -1.0,
                                  "fraction": 0.5,
                                  "band_width_mean_kmh": 20.0},
        }
        regime.update(over)
        race = {"season": 2023, "round": 1, "race_id": "r1",
                "circuit_name": "c1"}
        return _regime_signature(race, regime, "driver-a", "driver-b", "hh")

    def test_identical_structures_match_strongly(self):
        from racewise.data.historical.performance_patterns import _match_regimes

        sa = self._sig()
        sb = self._sig()
        # force different race identity via provenance-independent fields
        sb["race_identity"] = {"season": 2024, "round": 2, "race_id": "r2",
                               "circuit_id": None, "circuit_name": "c2"}
        m = _match_regimes(sa, sb)
        assert m["structure_state"] in ("STRONGLY_MATCHING_STRUCTURE",
                                        "MATCHING_STRUCTURE")
        assert m["structural_score"] is not None and m["structural_score"] > 0
        assert m["comparability"]["overall"] == "COMPARABLE"

    def test_slope_difference_beyond_tolerance_fails_component(self):
        from racewise.data.historical.performance_patterns import (
            _component_scores,
        )

        sa, sb = self._sig(), self._sig(slope_s_per_lap=0.9)
        c = _component_scores(sa, sb)
        assert c["slope_delta_s_per_lap"] == pytest.approx(0.78, abs=1e-6)
        assert c["slope_magnitude_match"] is False
        assert c["trend_match"] is True  # same sign

    def test_opposite_directions_fail_trend(self):
        from racewise.data.historical.performance_patterns import (
            _component_scores,
        )

        sa, sb = self._sig(), self._sig(slope_s_per_lap=-0.12,
                                        pattern="NARROWING")
        c = _component_scores(sa, sb)
        assert c["trend_match"] is False

    def test_structure_state_thresholds(self):
        from racewise.data.historical.performance_patterns import (
            _structure_state_from_score,
        )

        assert _structure_state_from_score(1.0, 5) == "STRONGLY_MATCHING_STRUCTURE"
        assert _structure_state_from_score(0.8, 5) == "MATCHING_STRUCTURE"
        assert _structure_state_from_score(0.6, 5) == "PARTIALLY_MATCHING_STRUCTURE"
        assert _structure_state_from_score(0.2, 5) == "NON_MATCHING_STRUCTURE"
        assert _structure_state_from_score(1.0, 2) == "INSUFFICIENT_EVIDENCE"

    def test_comparability_six_dimensions_present(self):
        from racewise.data.historical.performance_patterns import (
            COMPARABILITY_DIMENSIONS,
            _comparability,
        )

        comp = _comparability(self._sig(), self._sig())
        dims = [d["dimension"] for d in comp["dimensions"]]
        assert dims == list(COMPARABILITY_DIMENSIONS)
        assert comp["overall"] == "COMPARABLE"

    def test_comparability_partial_when_telemetry_missing_in_one(self):
        from racewise.data.historical.performance_patterns import _comparability

        sa = self._sig()
        sb = self._sig(telemetry_state="TELEMETRY_UNAVAILABLE",
                       telemetry_lap_count=0,
                       model_sensitivity={"status": "UNAVAILABLE",
                                          "delta_s": None, "fraction": 0.5,
                                          "band_width_mean_kmh": None})
        comp = _comparability(sa, sb)
        tel = next(d for d in comp["dimensions"]
                   if d["dimension"] == "TELEMETRY_COMPATIBILITY")
        assert tel["state"] == "PARTIALLY_COMPARABLE"
        assert tel["reasons"] == ["telemetry_missing_in_one_regime"]
        assert comp["overall"] == "PARTIALLY_COMPARABLE"

    def test_trajectory_states(self):
        from racewise.data.historical.performance_patterns import (
            _trajectory_comparison,
        )

        sa = self._sig()
        sb = self._sig()
        assert _trajectory_comparison(sa, sb)["state"] == "TRAJECTORY_COMPARABLE"
        sc = self._sig(delta_series=[[5, 0.5]])
        assert _trajectory_comparison(sa, sc)["state"] == "TRAJECTORY_UNAVAILABLE"


class TestAggregation:
    def _occ(self, hyp_status: str = "SUPPORTED", resid: str = "RESIDUAL_STABLE",
             sens: float | None = -1.0, season: int = 2023,
             round_num: int = 1) -> dict:
        return {
            "season": season, "round": round_num, "regime_index": 1,
            "circuit_name": "c1", "lap_range": "5-9",
            "trend_classification": "WIDENING", "slope_s_per_lap": 0.12,
            "lap_count": 5, "residual_state": resid, "residual_mean_s": 0.1,
            "envelope_width_mean_kmh": 20.0,
            "sensitivity_status": "VALID" if sens is not None else "UNAVAILABLE",
            "sensitivity_delta_s": sens, "sensitivity_parameter": 0.5,
            "telemetry_status": "AVAILABLE", "telemetry_lap_count": 5,
            "compound_summary": ["MEDIUM"], "stint_overlap": [1],
            "pit_overlap": False, "race_control_overlap": False,
            "hypothesis_state_summary": {"H1_corner_speed": hyp_status},
            "normalized_shape": [0.5, 0.6, 0.7],
            "pair_inverted_vs_canonical": False,
        }

    def test_hypothesis_consistency_states(self):
        from racewise.data.historical.performance_patterns import (
            _hypothesis_consistency,
        )

        occs = [self._occ("SUPPORTED"), self._occ("SUPPORTED", season=2024)]
        agg = _hypothesis_consistency(occs)
        assert agg["H1_corner_speed"]["consistency"] == "CONSISTENT"
        occs = [self._occ("SUPPORTED"), self._occ("NOT_SUPPORTED", season=2024)]
        agg = _hypothesis_consistency(occs)
        assert agg["H1_corner_speed"]["consistency"] == "VARIABLE"
        occs = [self._occ("SUPPORTED"), self._occ("CONTRADICTED", season=2024)]
        agg = _hypothesis_consistency(occs)
        assert agg["H1_corner_speed"]["consistency"] == "CONTRADICTORY"
        agg = _hypothesis_consistency([self._occ("INSUFFICIENT_EVIDENCE")])
        assert agg["H1_corner_speed"]["consistency"] == "INSUFFICIENT_EVIDENCE"

    def test_falsification_preserves_contradictions(self):
        from racewise.data.historical.performance_patterns import (
            _hypothesis_consistency,
            _pattern_falsification_summary,
        )

        occs = [self._occ("SUPPORTED"), self._occ("CONTRADICTED", season=2024)]
        summary = _pattern_falsification_summary(_hypothesis_consistency(occs))
        assert len(summary["supporting_refs"]) == 1
        assert len(summary["contradicting_refs"]) == 1
        assert "2024" in summary["contradicting_refs"][0]

    def test_residual_pattern_states(self):
        from racewise.data.historical.performance_patterns import (
            _residual_pattern,
        )

        assert _residual_pattern(
            [self._occ(resid="RESIDUAL_STABLE"),
             self._occ(resid="RESIDUAL_STABLE", season=2024)])["state"] \
            == "RESIDUAL_STABLE"
        assert _residual_pattern(
            [self._occ(resid="RESIDUAL_INCREASING"),
             self._occ(resid="RESIDUAL_DECREASING", season=2024)])["state"] \
            == "RESIDUAL_REVERSAL"
        assert _residual_pattern([self._occ()])["state"] == "INSUFFICIENT_EVIDENCE"

    def test_sensitivity_comparison_model_scoped(self):
        from racewise.data.historical.performance_patterns import (
            _sensitivity_comparison,
        )

        out = _sensitivity_comparison(
            [self._occ(sens=-1.0), self._occ(sens=-1.2, season=2024)])
        assert out["state"] == "MEASURED"
        assert out["sensitivity_spread_s"] == pytest.approx(0.2, abs=1e-9)
        assert "model property" in out["note"]
        out = _sensitivity_comparison([self._occ()])
        assert out["state"] == "INSUFFICIENT_EVIDENCE"

    def test_repeat_type(self):
        from racewise.data.historical.performance_patterns import _repeat_type

        assert _repeat_type([self._occ(), self._occ(round_num=2)]) \
            == "CROSS_RACE_REPEAT"
        assert _repeat_type([self._occ(), self._occ(season=2024, round_num=1)]) \
            == "CROSS_SEASON_REPEAT"

    def test_context_facets_descriptive_only(self):
        from racewise.data.historical.performance_patterns import (
            _context_facets,
        )

        facets = _context_facets([self._occ(), self._occ(round_num=2)])
        assert all("cause" not in f["facet"] for f in facets)
        assert all("note" not in f or "no causal role" in f.get("note", "")
                   for f in facets)


# ---------------------------------------------------------------------------
# tool boundary + live semantics (canonical DB)
# ---------------------------------------------------------------------------


@requires_db
class TestMcpBoundary:
    def test_tool_registered_with_bounds(self):
        from racewise.tools.historical import build_historical_registry
        from racewise.tools.contract import ToolError
        from racewise.data.historical.canonical_queries import CanonicalQueries

        reg = build_historical_registry(CanonicalQueries())
        name = "analyze_cross_race_performance_patterns"
        assert name in reg._tools
        base = {"driver_a": "max-verstappen", "driver_b": "sergio-perez"}
        for label, extra in (
            ("max_races_oob", {"max_races": 21}),
            ("max_races_zero", {"max_races": 0}),
            ("max_patterns_oob", {"max_patterns": 51}),
            ("same_driver", {"driver_b": "max-verstappen"}),
            ("seasons_not_list", {"seasons": 2023}),
            ("rounds_not_ints", {"rounds": ["a"]}),
            ("circuit_empty", {"circuit": "  "}),
            ("unknown_param", {"bogus": 1}),
        ):
            with pytest.raises(ToolError):
                reg.execute(name, {**base, **extra})

    def test_registry_happy_path_deterministic(self):
        from racewise.tools.historical import build_historical_registry
        from racewise.data.historical.canonical_queries import CanonicalQueries

        reg = build_historical_registry(CanonicalQueries())
        args = {"driver_a": "max-verstappen", "driver_b": "sergio-perez",
                "seasons": [2023], "max_races": 4}
        r1 = reg.execute("analyze_cross_race_performance_patterns", args)["output"]
        r2 = reg.execute("analyze_cross_race_performance_patterns", args)["output"]
        assert r1["status"] == "VALID"
        assert r1["output_hash"] == r2["output_hash"]
        assert r1["pattern_count"] >= 1

    def test_full_registry_tool_count(self):
        from racewise.tools.historical import build_historical_registry
        from racewise.data.historical.canonical_queries import CanonicalQueries

        reg = build_historical_registry(CanonicalQueries())
        assert len(reg._tools) == 27  # 23 pre-6O historical + 4 memory tools (Phase 6O)


@requires_db
class TestPatternsLive:
    @pytest.fixture(scope="class")
    def result2023(self):
        from racewise.data.historical.canonical_queries import get_canonical_queries
        from racewise.data.historical.performance_patterns import (
            analyze_cross_race_performance_patterns,
        )

        return analyze_cross_race_performance_patterns(
            get_canonical_queries(), "max-verstappen", "sergio-perez",
            seasons=[2023], max_races=4, max_patterns=20)

    def test_valid_with_recurring_patterns(self, result2023):
        r = result2023
        assert r["status"] == "VALID"
        assert r["corpus"]["eligible_races"] <= 4
        for p in r["patterns"]:
            assert p["independent_races"] >= 2
            assert p["recurrence_classification"] == "RECURRING"
            assert p["occurrence_count"] >= p["independent_races"]
            # every occurrence traceable to a 6K regime hash
            for ref in p["provenance"]["source_regime_refs"]:
                assert ref["regime_output_hash"]
            assert p["provenance"]["generated_at"] is None

    def test_no_ranking_no_confidence_language(self, result2023):
        """No unsupported claims anywhere in the payload. Negated/disclaimer
        phrasings (e.g. 'no confidence scores, no rankings') are checked for
        their negation markers so the methodology string stays honest while
        assertive uses stay banned."""
        payload = json.dumps(result2023).lower()
        i = payload.find("confidence")
        while i != -1:
            window = payload[max(0, i - 40):i]
            assert "no " in window or "never" in window, \
                "non-negated 'confidence' usage in payload"
            i = payload.find("confidence", i + 1)
        for banned in ("would have won", "caused the", "optimal",
                       "best race", "likely winner", "guaranteed"):
            assert banned not in payload

    def test_pattern_id_stability_across_invocations(self, result2023):
        from racewise.data.historical.canonical_queries import get_canonical_queries
        from racewise.data.historical.performance_patterns import (
            analyze_cross_race_performance_patterns,
        )

        r2 = analyze_cross_race_performance_patterns(
            get_canonical_queries(), "max-verstappen", "sergio-perez",
            seasons=[2023], max_races=4, max_patterns=20)
        assert r2["output_hash"] == result2023["output_hash"]
        ids1 = {p["pattern_id"] for p in result2023["patterns"]}
        ids2 = {p["pattern_id"] for p in r2["patterns"]}
        assert ids1 == ids2

    def test_negative_controls(self):
        from racewise.data.historical.canonical_queries import get_canonical_queries
        from racewise.data.historical.performance_patterns import (
            analyze_cross_race_performance_patterns,
        )

        q = get_canonical_queries()
        assert analyze_cross_race_performance_patterns(
            q, "max-verstappen", "max-verstappen")["status"] == "INVALID"
        assert analyze_cross_race_performance_patterns(
            q, "giuseppe-farina", "luigi-fagioli", seasons=[1950])["status"] \
            == "UNAVAILABLE"
        assert analyze_cross_race_performance_patterns(
            q, "lewis-hamilton", "sebastian-vettel", seasons=[2018])["status"] \
            == "UNAVAILABLE"
        assert analyze_cross_race_performance_patterns(
            q, "max-verstappen", "sergio-perez",
            seasons=[2023], rounds=[5], max_races=1)["status"] \
            == "INSUFFICIENT_EVIDENCE"
        assert analyze_cross_race_performance_patterns(
            q, "max-verstappen", "sergio-perez", max_races=0)["status"] \
            == "INVALID"

    def test_inversion_semantics_recorded(self, result2023):
        """Any occurrence whose 6K collection used the opposite pair order
        carries the flag and negated signed quantities (slope*lap_count
        sign consistent with the reported trend)."""
        for p in result2023["patterns"]:
            for o in p["occurrences"]:
                if o["pair_inverted_vs_canonical"]:
                    assert (o["slope_s_per_lap"] > 0) == \
                        (o["trend_classification"] == "WIDENING")
                    break


@requires_db
class TestApiEndpoint:
    def test_endpoint_valid_and_deterministic(self):
        from fastapi.testclient import TestClient
        from racewise.api.app import app

        c = TestClient(app)
        r1 = c.get("/api/catalog/performance-patterns",
                   params={"driver_a": "max-verstappen",
                           "driver_b": "sergio-perez", "seasons": "2023",
                           "max_races": 3})
        assert r1.status_code == 200
        assert r1.json()["status"] == "VALID"
        r2 = c.get("/api/catalog/performance-patterns",
                   params={"driver_a": "max-verstappen",
                           "driver_b": "sergio-perez", "seasons": "2023",
                           "max_races": 3})
        assert r1.content == r2.content

    def test_endpoint_bounds_and_validation(self):
        from fastapi.testclient import TestClient
        from racewise.api.app import app

        c = TestClient(app)
        assert c.get("/api/catalog/performance-patterns",
                     params={"max_races": 99}).status_code == 422
        assert c.get("/api/catalog/performance-patterns",
                     params={"seasons": "abc"}).status_code == 422
        assert c.get("/api/catalog/performance-patterns",
                     params={"driver_a": "max-verstappen",
                             "driver_b": "max-verstappen"}).status_code == 422
