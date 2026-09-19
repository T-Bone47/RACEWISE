"""Cross-provider validation: F1DB canonical data vs Jolpica cached data.

Compares overlapping fields and classifies each as MATCH / MISMATCH /
NOT_AVAILABLE without forcing agreement. Both values are preserved on
mismatch. Resolution policy: F1DB is the historical foundation of record;
Jolpica (Ergast successor) is a second opinion. Discrepancies are surfaced,
never silently overwritten.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class Comparison:
    """One compared field between two providers."""

    field: str
    provider_a: str
    provider_b: str
    value_a: Any
    value_b: Any
    classification: str  # MATCH | MISMATCH | NOT_AVAILABLE
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _classify(value_a: Any, value_b: Any, tolerance: float = 0.0) -> str:
    if value_a is None and value_b is None:
        return "NOT_AVAILABLE"
    if value_a is None or value_b is None:
        return "NOT_AVAILABLE"
    if isinstance(value_a, (int, float)) and isinstance(value_b, (int, float)):
        return "MATCH" if abs(float(value_a) - float(value_b)) <= tolerance else "MISMATCH"
    return "MATCH" if str(value_a).strip() == str(value_b).strip() else "MISMATCH"


class CrossProviderValidator:
    """Compares canonical F1DB sessions against cached Jolpica responses."""

    def __init__(self, queries: Any, jolpica_cache_dir: Optional[str] = None) -> None:
        self.queries = queries
        if jolpica_cache_dir is None:
            import os

            jolpica_cache_dir = os.environ.get(
                "RACEWISE_DATA_DIR", str(Path.cwd() / "data")
            )
        self.cache_dir = Path(jolpica_cache_dir) / "raw" / "jolpica"

    # -- Jolpica cache access -------------------------------------------------

    def find_jolpica_race(self, season: int, round_num: int) -> Optional[dict]:
        """Locate a cached Jolpica race payload by season/round scan."""
        if not self.cache_dir.exists():
            return None
        for path in sorted(self.cache_dir.glob("*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
            for race in races:
                if str(race.get("season")) == str(season) and str(race.get("round")) == str(round_num):
                    if "Results" in race:
                        return race
        return None

    # -- comparisons ------------------------------------------------------------

    def compare_race_metadata(self, season: int, round_num: int) -> list[Comparison]:
        """Compare event name, date, and circuit between providers."""
        canonical = self.queries.resolve_race(season, round_num=round_num)
        jolpica = self.find_jolpica_race(season, round_num)
        comparisons: list[Comparison] = []
        if canonical is None or jolpica is None:
            return [
                Comparison(
                    field="race",
                    provider_a="f1db",
                    provider_b="jolpica",
                    value_a=canonical is not None,
                    value_b=jolpica is not None,
                    classification="NOT_AVAILABLE",
                    note="One provider has no record of this race",
                )
            ]
        comparisons.append(
            Comparison(
                "date",
                "f1db",
                "jolpica",
                canonical.get("date"),
                jolpica.get("date"),
                _classify(canonical.get("date"), jolpica.get("date")),
            )
        )
        # Circuit naming differs structurally (key vs full name): compare only when both present.
        canonical_circuit = canonical.get("circuit_name")
        jolpica_circuit = (jolpica.get("Circuit") or {}).get("circuitName")
        comparisons.append(
            Comparison(
                "circuit",
                "f1db",
                "jolpica",
                canonical_circuit,
                jolpica_circuit,
                "NOT_AVAILABLE" if (canonical_circuit is None or jolpica_circuit is None) else "MISMATCH",
                note="Different identifier schemes (F1DB key vs Jolpica name); identity resolved via round/date",
            )
        )
        return comparisons

    def compare_race_results(self, season: int, round_num: int) -> list[Comparison]:
        """Compare finishing order and key fields driver-by-driver.

        Driver identity is resolved by position (finishing order) because
        constructor/driver id schemes differ between providers.
        """
        canonical_rows = self.queries.get_results(season, round_num, "RACE")
        jolpica_race = self.find_jolpica_race(season, round_num)
        if not canonical_rows or not jolpica_race:
            return [
                Comparison(
                    "race_results",
                    "f1db",
                    "jolpica",
                    len(canonical_rows) or None,
                    len(jolpica_race.get("Results", [])) if jolpica_race else None,
                    "NOT_AVAILABLE",
                    note="Provider lacks race results for this round",
                )
            ]

        jolpica_rows = jolpica_race["Results"]
        comparisons: list[Comparison] = []
        max_len = max(len(canonical_rows), len(jolpica_rows))

        def canon_pos(row: dict) -> Optional[int]:
            return row.get("position") if row.get("position") is not None else None

        def jolpica_pos(row: dict) -> Optional[int]:
            pos = row.get("position")
            try:
                return int(pos) if pos is not None else None
            except (TypeError, ValueError):
                return None

        # Compare finishing order (winner, podium, tail) by index.
        for i in range(min(len(canonical_rows), len(jolpica_rows))):
            c = canonical_rows[i]
            j = jolpica_rows[i]
            cp, jp = canon_pos(c), jolpica_pos(j)
            comparisons.append(
                Comparison(
                    f"position[{i}]",
                    "f1db",
                    "jolpica",
                    cp,
                    jp,
                    _classify(cp, jp),
                )
            )
            # Lap counts
            comparisons.append(
                Comparison(
                    f"laps[{i}]",
                    "f1db",
                    "jolpica",
                    c.get("laps"),
                    int(j["laps"]) if j.get("laps") else None,
                    _classify(c.get("laps"), int(j["laps"]) if j.get("laps") else None),
                )
            )
            # Points
            comparisons.append(
                Comparison(
                    f"points[{i}]",
                    "f1db",
                    "jolpica",
                    c.get("points"),
                    float(j["points"]) if j.get("points") else None,
                    _classify(c.get("points"), float(j["points"]) if j.get("points") else None, tolerance=0.001),
                )
            )
            # Total time in ms (winner usually)
            c_ms = c.get("milliseconds")
            j_ms = int(j["Time"]["millis"]) if isinstance(j.get("Time"), dict) and j["Time"].get("millis") else None
            comparisons.append(
                Comparison(
                    f"time_millis[{i}]",
                    "f1db",
                    "jolpica",
                    c_ms,
                    j_ms,
                    _classify(c_ms, j_ms),
                )
            )
        # Coverage difference
        if len(canonical_rows) != len(jolpica_rows):
            comparisons.append(
                Comparison(
                    "n_results",
                    "f1db",
                    "jolpica",
                    len(canonical_rows),
                    len(jolpica_rows),
                    "MISMATCH",
                    note=f"Coverage difference: f1db={len(canonical_rows)} jolpica={len(jolpica_rows)} (both values preserved)",
                )
            )
        return comparisons

    def validate_race(self, season: int, round_num: int) -> dict:
        """Full validation report for one race."""
        comparisons = self.compare_race_metadata(season, round_num) + self.compare_race_results(
            season, round_num
        )
        summary = {"MATCH": 0, "MISMATCH": 0, "NOT_AVAILABLE": 0}
        for c in comparisons:
            summary[c.classification] = summary.get(c.classification, 0) + 1
        mismatches = [c.to_dict() for c in comparisons if c.classification == "MISMATCH"]
        return {
            "season": season,
            "round": round_num,
            "providers": ["f1db", "jolpica"],
            "total_compared": len(comparisons),
            "summary": summary,
            "resolution_policy": (
                "F1DB is the historical foundation of record; mismatches preserve both "
                "values and are surfaced for review, never silently merged."
            ),
            "mismatches": mismatches,
            "comparisons": [c.to_dict() for c in comparisons],
        }
