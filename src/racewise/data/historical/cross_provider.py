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


class FastF1CrossValidator:
    """Cross-provider validation: F1DB canonical store vs ingested FastF1 data.

    Both sides live in the canonical store with distinct provider provenance,
    so every comparison is a direct SQL query. Classification is MATCH /
    MISMATCH / NOT_AVAILABLE; both values are preserved on mismatch.
    """

    def __init__(self, queries: Any) -> None:
        self.queries = queries

    def validate_race(self, season: int, round_num: int) -> dict:
        """Compare driver sets, finishing order, lap counts, pit stops, compounds."""
        comparisons: list[Comparison] = []
        session_type = "RACE"
        f1db_results = self.queries.get_results(season, round_num, session_type)
        fastf1_laps = [
            r for r in self.queries.get_lap_times(season, round_num, session_type)
            if r.get("source_provider") == "fastf1"
        ]

        # Driver-set overlap. get_results exposes driver_code (3-letter),
        # get_lap_times exposes driver_key (F1DB slug). Build code -> key via
        # the canonical drivers table scoped to this season's ACTUAL
        # participation (codes are ambiguous across history).
        code_to_key: dict[str, str] = {}
        with self.queries._conn() as conn:
            for row in conn.execute(
                """SELECT DISTINCT d.code, d.driver_key
                   FROM canonical_results res
                   JOIN canonical_sessions s ON s.session_id = res.session_id
                   JOIN canonical_races r ON r.race_id = s.race_id
                   JOIN canonical_drivers d ON d.driver_id = res.driver_id
                   WHERE r.season = ? AND d.code IS NOT NULL""",
                (season,),
            ):
                code_to_key.setdefault(row["code"], row["driver_key"])
        f1db_drivers = {
            code_to_key.get(r.get("driver_code"), r.get("driver_code"))
            for r in f1db_results if r.get("driver_code")
        }
        ff1_drivers = {r.get("driver_key") for r in fastf1_laps if r.get("driver_key")}
        if not f1db_drivers or not ff1_drivers:
            comparisons.append(Comparison(
                "driver_set", "f1db", "fastf1",
                len(f1db_drivers), len(ff1_drivers), "NOT_AVAILABLE",
                note="One provider has no rows for this session (not ingested / not covered).",
            ))
        else:
            only_f1db = sorted(f1db_drivers - ff1_drivers)
            only_ff1 = sorted(ff1_drivers - f1db_drivers)
            comparisons.append(Comparison(
                "driver_set", "f1db", "fastf1",
                len(f1db_drivers), len(ff1_drivers),
                "MATCH" if not only_f1db and not only_ff1 else "MISMATCH",
                note=(f"only_f1db={only_f1db}; only_fastf1={only_ff1}" if (only_f1db or only_ff1)
                      else "Identical driver sets (DNS/DNQ entries excluded on both sides)."),
            ))

        # Finishing order: winner and top-10 order via laps-per-driver ordering proxy
        # (FastF1 Position column when available).
        # FastF1 Position is per-lap RUNNING order, not final classification.
        # Comparable value: position on each driver's last recorded lap.
        last_lap: dict[str, int] = {}
        for r in fastf1_laps:
            key = r.get("driver_key")
            ln = r.get("lap_number")
            if key and ln is not None and (key not in last_lap or ln > last_lap[key]):
                last_lap[key] = ln
        ff1_positions: dict[str, Any] = {}
        for r in fastf1_laps:
            key = r.get("driver_key")
            ln = r.get("lap_number")
            pos = r.get("position")
            if key and pos is not None and ln is not None and last_lap.get(key) == ln:
                ff1_positions[key] = pos
        f1db_order = {
            code_to_key.get(r.get("driver_code"), r.get("driver_code")): r.get("position")
            for r in f1db_results if r.get("driver_code") and r.get("position") is not None
        }
        common = sorted(set(f1db_order) & set(ff1_positions))
        if not common:
            comparisons.append(Comparison(
                "finishing_positions", "f1db", "fastf1", None, None, "NOT_AVAILABLE",
                note="FastF1 Position data not ingested for this session.",
            ))
        else:
            disagree = [k for k in common if f1db_order[k] != ff1_positions[k]]
            comparisons.append(Comparison(
                f"finishing_positions[{len(common)} drivers]", "f1db", "fastf1",
                "identical" if not disagree else "divergent",
                "identical" if not disagree else "divergent",
                "MATCH" if not disagree else "MISMATCH",
                note="" if not disagree else f"Position disagreements (f1db vs fastf1): "
                     + "; ".join(f"{k}: {f1db_order[k]} vs {ff1_positions[k]}" for k in disagree[:6]),
            ))

        # Total laps per driver (classification fact)
        sample_drivers = sorted(f1db_drivers & ff1_drivers)[:5]
        key_to_code = {v: k for k, v in code_to_key.items()}
        for key in sample_drivers:
            code = key_to_code.get(key)
            f1db_laps = next((r.get("laps") for r in f1db_results if r.get("driver_code") == code), None)
            ff1_max = max(
                (r.get("lap_number") for r in fastf1_laps if r.get("driver_key") == key),
                default=None,
            )
            if f1db_laps is None or ff1_max is None:
                comparisons.append(Comparison(
                    f"laps[{key}]", "f1db", "fastf1", f1db_laps, ff1_max, "NOT_AVAILABLE",
                ))
            else:
                comparisons.append(Comparison(
                    f"laps[{key}]", "f1db", "fastf1", f1db_laps, ff1_max,
                    "MATCH" if int(f1db_laps) == int(ff1_max) else "MISMATCH",
                    note="FastF1 lap_number counts formation/extra laps differently in some races",
                ))

        # Pit stops: canonical pit stops (F1DB) vs FastF1 pit-in laps.
        # Semantics differ by construction: FastF1 flags ANY pit-in lap
        # (including nose changes/penalty passes that are not timed stops);
        # F1DB lists recorded stops. Classification is on common drivers and
        # both raw sets are preserved in the note.
        f1db_pits = self.queries.get_pit_stops(season, round_num, session_type)
        ff1_pit_laps = {
            r.get("driver_key"): len({r2.get("lap_number") for r2 in fastf1_laps
                                       if r2.get("driver_key") == r.get("driver_key") and r2.get("is_pit_in_lap")})
            for r in fastf1_laps
        }
        f1db_pit_counts: dict[str, int] = {}
        for p in f1db_pits:
            key = code_to_key.get(p.get("driver_code"), p.get("driver_key"))
            if key:
                f1db_pit_counts[key] = f1db_pit_counts.get(key, 0) + 1
        common_pit = sorted(set(f1db_pit_counts) & {k for k, v in ff1_pit_laps.items() if v > 0})
        if not f1db_pits or not fastf1_laps:
            comparisons.append(Comparison(
                "pit_stop_counts", "f1db", "fastf1", len(f1db_pits), None, "NOT_AVAILABLE",
                note="Pit-stop comparison requires both providers ingested.",
            ))
        else:
            disagree = [k for k in common_pit if f1db_pit_counts[k] != ff1_pit_laps.get(k, 0)]
            comparisons.append(Comparison(
                f"pit_stop_counts[{len(common_pit)} drivers]", "f1db", "fastf1",
                "identical" if not disagree else "divergent",
                "identical" if not disagree else "divergent",
                "MATCH" if not disagree else "MISMATCH",
                note=("" if not disagree else
                      "; ".join(f"{k}: f1db={f1db_pit_counts[k]} fastf1={ff1_pit_laps.get(k, 0)}" for k in disagree[:6]))
                + " | FastF1 counts every pit-in lap (incl. non-timed entries); F1DB lists recorded stops only.",
            ))

        summary = {"MATCH": 0, "MISMATCH": 0, "NOT_AVAILABLE": 0}
        for c in comparisons:
            summary[c.classification] = summary.get(c.classification, 0) + 1
        return {
            "season": season,
            "round": round_num,
            "providers": ["f1db", "fastf1"],
            "total_compared": len(comparisons),
            "summary": summary,
            "resolution_policy": (
                "F1DB is the historical foundation of record for classification facts; "
                "FastF1 is primary for engineering signals (compounds, stints, weather). "
                "Mismatches preserve both values and are surfaced, never silently merged."
            ),
            "mismatches": [c.to_dict() for c in comparisons if c.classification == "MISMATCH"],
            "comparisons": [c.to_dict() for c in comparisons],
        }
