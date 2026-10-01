"""Stitch-integration API tests.

Covers the two additive backend extensions from the Stitch reconciliation
(docs/STITCH_RACEWISE_FEATURE_RECONCILIATION.md §Backend extensions):

1. GET /api/catalog/session-context/{season}/{round} - real measured
   session context (stints, weather, telemetry coverage) for the
   investigation context strip. No fabrication, honest UNAVAILABLE facets.

2. include_profile opt-in on GET /api/catalog/counterfactual - bounded
   deterministic profile samples for the telemetry trace canvas. Default
   OFF keeps the canonical payload (and its output_hash) unchanged.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "canonical" / "canonical.db"
requires_db = pytest.mark.skipif(not DB_PATH.exists(),
                                 reason="canonical DB not present")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from racewise.api.app import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# session-context
# ---------------------------------------------------------------------------


@requires_db
class TestSessionContext:
    def test_real_session_context_shape(self, client):
        r = client.get("/api/catalog/session-context/2023/1")
        assert r.status_code == 200
        data = r.json()
        assert data["season"] == 2023 and data["round"] == 1
        assert data["session_type"] == "RACE"
        # session identity: the real canonical catalog row (no fabricated fields)
        assert isinstance(data["session"]["session_id"], str) and len(data["session"]["session_id"]) > 0
        assert data["session"]["season"] == 2023
        assert data["session"]["race_name"]
        # stints: measured windows with compound, ordered per driver
        assert isinstance(data["stints_by_driver"], dict)
        for driver_key, windows in data["stints_by_driver"].items():
            assert windows == sorted(windows, key=lambda w: w["stint_number"])
            for w in windows:
                assert {"stint_number", "compound", "lap_start", "lap_end"} <= set(w)
        # weather: measured values only, never extrapolated
        assert data["weather"]["status"] in ("AVAILABLE", "UNAVAILABLE")
        if data["weather"]["status"] == "AVAILABLE":
            assert data["weather"]["observations"] > 0
            assert data["weather"]["air_temp_c_first"] is not None
        # telemetry coverage: bounded policy facts
        tel = data["telemetry"]
        assert tel["available"] is True  # 2023 R1 has ingested telemetry
        assert tel["analysis_grid_s"] == 0.25
        assert len(tel["covered_laps"]) > 0
        # provenance: real tables only
        assert "canonical_stints" in data["provenance"]["tables"]

    def test_deterministic(self, client):
        a = client.get("/api/catalog/session-context/2023/1").json()
        b = client.get("/api/catalog/session-context/2023/1").json()
        assert a == b

    def test_unknown_session_404(self, client):
        assert client.get("/api/catalog/session-context/1899/1").status_code == 404

    def test_invalid_session_type_422(self, client):
        r = client.get("/api/catalog/session-context/2023/1?session_type=FREE_PRACTICE_1")
        assert r.status_code == 422

    def test_qualifying_session_context(self, client):
        """Qualifying is a supported canonical session type (Phase 6S)."""
        r = client.get("/api/catalog/session-context/2023/1?session_type=QUALIFYING")
        assert r.status_code == 200
        assert r.json()["session_type"] == "QUALIFYING"

    def test_measured_per_lap_facts_for_scope_drivers(self, client):
        """drivers= returns the measured per-lap rows (position, compound,
        tyre life) the context strip renders - real rows, bounded to <= 4
        drivers, empty list when a driver has no laps (never fabricated)."""
        r = client.get("/api/catalog/session-context/2023/1"
                       "?drivers=max-verstappen,sergio-perez")
        assert r.status_code == 200
        data = r.json()
        laps = data["laps_by_driver"]["max-verstappen"]
        assert len(laps) > 0
        for lap in laps:
            assert {"lap_number", "position", "time_s", "compound", "tyre_life"} <= set(lap)
        assert all(isinstance(l["lap_number"], int) for l in laps)
        # unknown driver: honest empty, not an error, not invented rows
        r2 = client.get("/api/catalog/session-context/2023/1?drivers=nonexistent-driver")
        assert r2.status_code == 200
        assert r2.json()["laps_by_driver"]["nonexistent-driver"] == []

    def test_no_fabricated_values(self, client):
        """Every rendered value must be a measured fact: no synthetic
        weather, no invented slices, no version strings."""
        data = client.get("/api/catalog/session-context/2023/1").json()
        body = json.dumps(data)
        for banned in ("100Hz", "100 Hz", "42k slices", "AeroDelta", "P=0.", "99.8%"):
            assert banned not in body


# ---------------------------------------------------------------------------
# counterfactual include_profile (opt-in)
# ---------------------------------------------------------------------------


@requires_db
class TestCounterfactualProfileSamples:
    def test_default_payload_unchanged_no_samples(self, client):
        r = client.get("/api/catalog/counterfactual/2023/1?fraction=0.5")
        assert r.status_code == 200
        data = r.json()
        if data.get("status") == "VALID":
            assert "profile_samples" not in data

    def test_include_profile_bounded_and_shaped(self, client):
        r = client.get("/api/catalog/counterfactual/2023/1?fraction=0.5&include_profile=true")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "VALID", data.get("reason")
        ps = data["profile_samples"]
        n = ps["n_samples"]
        assert n <= ps["cap"] <= 192
        assert len(ps["t_s"]) == len(ps["target_kmh"]) == len(ps["counterfactual_kmh"])
        assert ps["reference_kmh"] is not None
        assert len(ps["reference_kmh"]) == n
        # samples stay inside the measured summary envelope
        assert abs(ps["t_s"][0] - 0.0) < 5.0  # lap-relative grid starts near 0
        assert ps["n_total_points"] >= n

    def test_include_profile_deterministic(self, client):
        a = client.get("/api/catalog/counterfactual/2023/1?fraction=0.5&include_profile=true").json()
        b = client.get("/api/catalog/counterfactual/2023/1?fraction=0.5&include_profile=true").json()
        assert a["output_hash"] == b["output_hash"]
        assert a["profile_samples"] == b["profile_samples"]

    def test_default_hash_unchanged_by_new_flag(self, client):
        """The default (include_profile off) payload must hash identically
        whether or not the flag is explicitly false - the canonical payload
        is untouched by the extension."""
        a = client.get("/api/catalog/counterfactual/2023/1?fraction=0.5").json()
        b = client.get("/api/catalog/counterfactual/2023/1?fraction=0.5&include_profile=false").json()
        assert a["output_hash"] == b["output_hash"]

    def test_hash_self_consistent_with_samples(self, client):
        data = client.get(
            "/api/catalog/counterfactual/2023/1?fraction=0.5&include_profile=true").json()
        body = {k: v for k, v in data.items() if k != "output_hash"}
        expect = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:16]
        assert data["output_hash"] == expect

    def test_identity_fraction_samples_equal_baseline(self, client):
        """At f=0 the counterfactual samples must equal the baseline samples:
        the transformation is exact, the serialization changes nothing."""
        data = client.get(
            "/api/catalog/counterfactual/2023/1?fraction=0.0&include_profile=true").json()
        assert data["status"] == "VALID"
        ps = data["profile_samples"]
        assert ps["counterfactual_kmh"] == ps["target_kmh"]
        assert data["counterfactual_delta_s"] == 0.0


# ---------------------------------------------------------------------------
# unit-level: _profile_samples decimation
# ---------------------------------------------------------------------------


class TestProfileSampleDecimation:
    def test_short_grid_kept_intact(self):
        from racewise.data.historical.counterfactual import _profile_samples
        grid = [round(i * 0.25, 4) for i in range(50)]
        vals = [100.0 + i for i in range(50)]
        ps = _profile_samples(grid, vals, None, vals)
        assert ps["n_samples"] == 50
        assert ps["t_s"] == grid
        assert ps["reference_kmh"] is None

    def test_long_grid_decimated_deterministically(self):
        from racewise.data.historical.counterfactual import _profile_samples
        grid = [round(i * 0.25, 4) for i in range(400)]
        vals = [100.0 + (i % 40) for i in range(400)]
        ps1 = _profile_samples(grid, vals, vals, vals)
        ps2 = _profile_samples(grid, vals, vals, vals)
        assert ps1 == ps2                      # pure function of inputs
        assert ps1["n_samples"] <= ps1["cap"]
        assert ps1["t_s"][0] == grid[0]       # span endpoints preserved
        assert ps1["t_s"][-1] == grid[-1]
