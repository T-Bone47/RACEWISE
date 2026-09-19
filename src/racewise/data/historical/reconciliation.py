"""Reconciliation: cross-source validation and conflict resolution.

Compares data from multiple providers and classifies agreements/discrepancies.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DiscrepancyType:
    MATCH = "MATCH"
    EXPECTED_DIFFERENCE = "EXPECTED_DIFFERENCE"
    DISCREPANCY = "DISCREPANCY"
    MISSING_SOURCE = "MISSING_SOURCE"
    SOURCE_COVERAGE_DIFFERENCE = "SOURCE_COVERAGE_DIFFERENCE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass
class Discrepancy:
    field: str
    provider_a: str
    provider_b: str
    value_a: Any
    value_b: Any
    difference: Any
    tolerance: Optional[float]
    classification: str
    explanation: str
    timestamp: str = datetime.utcnow().isoformat()


class Reconciler:
    """Compares data from multiple providers and classifies discrepancies."""

    def __init__(self, tolerance_config: Optional[dict] = None):
        self.tolerance_config = tolerance_config or {
            "lap_time_s": 0.001,  # 1ms tolerance
            "position": 0,
            "points": 0,
            "lap_number": 0,
            "pit_in_lap": 0,
        }

    def compare_values(
        self,
        field: str,
        value_a: Any,
        value_b: Any,
        provider_a: str,
        provider_b: str,
        tolerance: Optional[float] = None,
    ) -> Discrepancy:
        """Compare two values and classify the discrepancy."""
        tol = tolerance or self.tolerance_config.get(field, 0)

        if value_a is None and value_b is None:
            return Discrepancy(
                field=field,
                provider_a=provider_a,
                provider_b=provider_b,
                value_a=value_a,
                value_b=value_b,
                difference=None,
                tolerance=tol,
                classification=DiscrepancyType.MATCH,
                explanation="Both values are None",
            )

        if value_a is None:
            return Discrepancy(
                field=field,
                provider_a=provider_a,
                provider_b=provider_b,
                value_a=value_a,
                value_b=value_b,
                difference="MISSING_IN_A",
                tolerance=tol,
                classification=DiscrepancyType.MISSING_SOURCE,
                explanation=f"Missing in {provider_a}, present in {provider_b}",
            )

        if value_b is None:
            return Discrepancy(
                field=field,
                provider_a=provider_a,
                provider_b=provider_b,
                value_a=value_a,
                value_b=value_b,
                difference="MISSING_IN_B",
                tolerance=tol,
                classification=DiscrepancyType.MISSING_SOURCE,
                explanation=f"Present in {provider_a}, missing in {provider_b}",
            )

        # Both present - compare
        if field in ("lap_time_s",):
            try:
                diff = abs(float(value_a) - float(value_b))
                if diff <= tolerance:
                    return Discrepancy(
                        field=field,
                        provider_a=provider_a,
                        provider_b=provider_b,
                        value_a=value_a,
                        value_b=value_b,
                        difference=diff,
                        tolerance=tol,
                        classification=DiscrepancyType.MATCH,
                        explanation=f"Values match within tolerance ({diff} <= {tol})",
                    )
                else:
                    return Discrepancy(
                        field=field,
                        provider_a=provider_a,
                        provider_b=provider_b,
                        value_a=value_a,
                        value_b=value_b,
                        difference=diff,
                        tolerance=tol,
                        classification=DiscrepancyType.DISCREPANCY,
                        explanation=f"Values differ beyond tolerance ({diff} > {tol})",
                    )
            except (TypeError, ValueError):
                pass

        # Exact match for other fields
        if value_a == value_b:
            return Discrepancy(
                field=field,
                provider_a=provider_a,
                provider_b=provider_b,
                value_a=value_a,
                value_b=value_b,
                difference=None,
                tolerance=0,
                classification=DiscrepancyType.MATCH,
                explanation="Exact match",
            )

        # Check for expected differences (e.g., different precision)
        if field in ("lap_time_s",) and self._is_expected_difference(value_a, value_b):
            return Discrepancy(
                field=field,
                provider_a=provider_a,
                provider_b=provider_b,
                value_a=value_a,
                value_b=value_b,
                difference=str(value_a) + " vs " + str(value_b),
                tolerance=tol,
                classification=DiscrepancyType.EXPECTED_DIFFERENCE,
                explanation="Expected difference due to source precision/format",
            )

        return Discrepancy(
            field=field,
            provider_a=provider_a,
            provider_b=provider_b,
            value_a=value_a,
            value_b=value_b,
            difference=str(value_a) + " vs " + str(value_b),
            tolerance=tol,
            classification=DiscrepancyType.DISCREPANCY,
            explanation="Values differ",
        )

    def _is_expected_difference(self, a: Any, b: Any) -> bool:
        """Check if difference is expected (e.g., precision differences)."""
        try:
            fa, fb = float(a), float(b)
            # If they're very close but not exactly equal, might be precision
            diff = abs(fa - fb)
            return 0 < diff < 0.01  # Less than 10ms difference
        except (TypeError, ValueError):
            return False

    def compare_race_results(
        self,
        result_a: dict,
        result_b: dict,
        provider_a: str,
        provider_b: str,
    ) -> list[Discrepancy]:
        """Compare two race results."""
        discrepancies = []
        fields = ["position", "points", "laps", "time", "grid", "driver_id", "constructor_id"]

        for field in fields:
            val_a = result_a.get(field)
            val_b = result_b.get(field)
            disc = self.compare_values(field, val_a, val_b, provider_a, provider_b)
            if disc.classification != DiscrepancyType.MATCH:
                discrepancies.append(disc)

        return discrepancies

    def compare_lap_times(
        self,
        laps_a: list[dict],
        laps_b: list[dict],
        provider_a: str,
        provider_b: str,
    ) -> list[Discrepancy]:
        """Compare lap times from two providers."""
        discrepancies = []

        # Build lookup by driver and lap number
        laps_a = {(l["driver"], l["lap_number"]): l for l in laps_a if l.get("driver") and l.get("lap_number")}
        laps_b = {(l["driver"], l["lap_number"]): l for l in laps_b if l.get("driver") and l.get("lap_number")}

        all_keys = set(laps_a.keys()) | set(laps_b.keys())

        for key in all_keys:
            lap_a = laps_a.get(key)
            lap_b = laps_b.get(key)

            if lap_a is None:
                discrepancies.append(Discrepancy(
                    field="lap_time_s",
                    provider_a=provider_a,
                    provider_b=provider_b,
                    value_a=None,
                    value_b=lap_b.get("lap_time_s"),
                    difference="MISSING_IN_A",
                    tolerance=0.001,
                    classification=DiscrepancyType.MISSING_SOURCE,
                    explanation=f"Lap missing in {provider_a}",
                ))
                continue

            if lap_b is None:
                discrepancies.append(Discrepancy(
                    field="lap_time_s",
                    provider_a=provider_a,
                    provider_b=provider_b,
                    value_a=lap_a.get("lap_time_s"),
                    value_b=None,
                    difference="MISSING_IN_B",
                    tolerance=0.001,
                    classification=DiscrepancyType.MISSING_SOURCE,
                    explanation=f"Lap missing in {provider_b}",
                ))
                continue

            # Compare lap times
            disc = self.compare_values("lap_time_s", lap_a.get("lap_time_s"), lap_b.get("lap_time_s"), provider_a, provider_b)
            discrepancies.append(disc)

            # Compare sectors if available
            for sector in ["sector_1_s", "sector_2_s", "sector_3_s"]:
                disc = self.compare_values(sector, lap_a.get(sector), lap_b.get(sector), provider_a, provider_b)
                if disc.classification != "MATCH":
                    discrepancies.append(disc)

        return discrepancies

    def compare_pit_stops(
        self,
        stops_a: list[dict],
        stops_b: list[dict],
        provider_a: str,
        provider_b: str,
    ) -> list[Discrepancy]:
        discrepancies = []

        # Build lookup by driver + lap
        stops_a = {(s["driver"], s["pit_in_lap"]): s for s in stops_a}
        stops_b = {(s["driver"], s["pit_in_lap"]): s for s in stops_b}

        all_keys = set(stops_a.keys()) | set(stops_b.keys())

        for key in all_keys:
            stop_a = stops_a.get(key)
            stop_b = stops_b.get(key)

            if stop_a is None:
                discrepancies.append(Discrepancy(
                    field="pit_stop",
                    provider_a=provider_a,
                    provider_b=provider_b,
                    value_a=None,
                    value_b=stop_b,
                    difference="MISSING_IN_A",
                    classification=DiscrepancyType.MISSING_SOURCE,
                    explanation=f"Pit stop missing in {provider_a}",
                ))
                continue

            if stop_b is None:
                discrepancies.append(Discrepancy(
                    field="pit_stop",
                    provider_a=provider_a,
                    provider_b=provider_b,
                    value_a=stop_a,
                    value_b=None,
                    difference="MISSING_IN_B",
                    classification=DiscrepancyType.MISSING_SOURCE,
                    explanation=f"Pit stop missing in {provider_b}",
                ))
                continue

            # Compare pit stop times
            for field in ["lap", "time", "duration"]:
                val_a = stop_a.get(field)
                val_b = stop_b.get(field)
                disc = self.compare_values(field, val_a, val_b, provider_a, provider_b)
                if disc.classification != "MATCH":
                    discrepancies.append(disc)

        return discrepancies

    def compare_sessions(
        self,
        session_a: dict,
        session_b: dict,
        provider_a: str,
        provider_b: str,
    ) -> list[Discrepancy]:
        """Compare session metadata."""
        discrepancies = []
        fields = ["event_name", "circuit", "date", "total_laps"]

        for field in fields:
            disc = self.compare_values(field, session_a.get(field), session_b.get(field), provider_a, provider_b)
            if disc.classification != "MATCH":
                discrepancies.append(disc)

        return discrepancies


def reconcile_sources(
    provider_data: dict[str, dict],
    base_provider: str = "fastf1",
) -> dict[str, Any]:
    """Reconcile multiple provider data into a unified view with discrepancy report."""
    providers = list(provider_data.keys())
    if base_provider not in providers:
        base_provider = providers[0]

    reconciler = Reconciler()
    base_data = provider_data[base_provider]
    other_providers = [p for p in providers if p != base_provider]

    report = {
        "base_provider": base_provider,
        "compared_providers": other_providers,
        "timestamp": datetime.utcnow().isoformat(),
        "discrepancies": [],
        "summary": {
            "total_compared": 0,
            "matches": 0,
            "expected_differences": 0,
            "discrepancies": 0,
            "missing_sources": 0,
        },
    }

    # Compare each provider against base
    for other in other_providers:
        other_data = provider_data[other]

        # Compare race results if available
        if "race_results" in base_data and "race_results" in provider_data[other]:
            for base_result in base_data["race_results"]:
                other_result = next((r for r in provider_data[other]["race_results"]
                                   if r.get("driver_id") == base_result.get("driver_id")), None)
                if other_result:
                    discrepancies = Reconciler().compare_race_results(
                        base_result, other_result, base_provider, other
                    )
                    for disc in discrepancies:
                        report["discrepancies"].append(disc)
                        report["summary"]["total_compared"] += 1
                        if disc.classification == "MATCH":
                            report["summary"]["matches"] += 1
                        elif disc.classification == "EXPECTED_DIFFERENCE":
                            report["summary"]["expected_differences"] += 1
                        elif disc.classification == "DISCREPANCY":
                            report["summary"]["discrepancies"] += 1
                        elif disc.classification in ("MISSING_SOURCE", "SOURCE_COVERAGE_DIFFERENCE"):
                            report["summary"]["missing_sources"] += 1

    return report