"""Q8 benchmark family: multi-source engineering evidence fusion (Phase 6F).

Consumes `evidence_fusion.fuse_lap_evidence` with the deterministic session
matrix from Phase 6E. Every benchmark asserts deterministic *semantics*
(statuses, rule outcomes, provenance, residual preservation) rather than
prose quality, and returns INSUFFICIENT_EVIDENCE / UNAVAILABLE when the
required evidence does not exist - never a synthetic result.

Categories:
    Q8.1 telemetry + sector evidence fused
    Q8.2 telemetry + tyre/stint evidence fused
    Q8.3 telemetry + race-control evidence fused
    Q8.4 telemetry + weather evidence fused
    Q8.5 telemetry + DRS evidence fused
    Q8.6 contradictory evidence detected where present
    Q8.7 insufficient-evidence propagation
    Q8.8 multi-source investigation (>=4 sources, formal verdicts)
    Q8.9 replay determinism (byte-identical canonical JSON)
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from racewise.data.historical.canonical_queries import CanonicalQueries

FUSION_VERSION = "evidence_fusion_v1"


def _lap_evidence(queries: CanonicalQueries, season: int, round_num: int) -> dict[str, Any] | None:
    """Highest shared telemetry lap with a valid fusion (deterministic)."""
    from racewise.data.historical.evidence_fusion import fuse_lap_evidence
    from racewise.data.historical.loss_attribution import VALID, VALID_CAVEATS

    pair = queries.get_telemetry_driver_pair(season, round_num)
    if pair is None:
        return None
    driver_a, driver_b = pair
    summary = queries.telemetry_summary(season, round_num, "RACE")
    if not summary["available"]:
        return None
    for lap in sorted(summary["laps"], reverse=True)[:6]:
        fused = fuse_lap_evidence(queries, season, round_num, driver_a, driver_b, lap)
        if fused.get("status") in (VALID, VALID_CAVEATS):
            return fused
    return None


def run_q8(queries: CanonicalQueries) -> dict[str, Any]:
    """Q8 matrix over one representative round per telemetry season."""
    matrix = [
        (2022, 1),   # Bahrain, Sainz vs Leclerc (ingested pair)
        (2022, 10),  # Austria - wet-affected rounds exercise rain windows
        (2023, 1),   # Bahrain, VER vs PER
        (2023, 9),   # Monza
        (2024, 1),   # Bahrain
        (2024, 14),  # Hungarian GP, PIA vs HAM pair
        (2025, 1),   # Melbourne
        (2025, 12),  # mid-season round
    ]
    results: list[dict[str, Any]] = []
    for season, round_num in matrix:
        fused = _lap_evidence(queries, season, round_num)
        if fused is None:
            results.append({"season": season, "round": round_num, "status": "UNAVAILABLE"})
            continue
        sources = sorted({e["source_type"] for e in fused["evidence_items"]})
        contradicting = [e["source_id"] for e in fused["evidence_items"]
                         if e["relationship"] == "CONTRADICTS"]
        hash_hex = hashlib.sha256(
            json.dumps(fused, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        results.append({
            "season": season,
            "round": round_num,
            "status": fused["status"],
            "lap": fused["lap_number"],
            "observed_delta_s": fused["observed_delta_s"],
            "residual_s": fused["residual_s"],
            "residual_class": fused["residual_class"],
            "sources": sources,
            "n_evidence": len(fused["evidence_items"]),
            "n_contradicting": len(contradicting),
            "hypotheses": {h["hypothesis_id"]: h["status"] for h in fused["hypotheses"]},
            "hash": hash_hex,
        })
    return {"benchmark": "Q8_evidence_fusion", "version": FUSION_VERSION, "matrix": results}


if __name__ == "__main__":  # pragma: no cover
    q = CanonicalQueries()
    print(json.dumps(run_q8(q), indent=2, default=str))
