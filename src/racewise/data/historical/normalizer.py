"""Normalizer: converts provider-specific data into canonical RACEWISE schemas.

All provider-specific data is normalized into canonical RACEWISE schemas at the
adapter boundary. The rest of the system never sees provider-specific structures.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import pandas as pd

from racewise.domain.schemas import (
    Lap,
    PitStop,
    Stint,
    WeatherRecord,
    RaceControlEvent,
    SessionSummary,
    Stint,
)

logger = logging.getLogger(__name__)


def _to_float(value: Any) -> Optional[float]:
    """Safely convert to float."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    """Safely convert to int."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool:
    """Safely convert to bool."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "y")
    return bool(value)


class Normalizer:
    """Normalizes provider-specific data to canonical RACEWISE schemas."""

    # --- F1DB normalization ---

    @staticmethod
    def f1db_race_result(row: dict) -> dict:
        """Normalize an F1DB race result row."""
        return {
            "season": row.get("season"),
            "round": row.get("round"),
            "driver_id": row.get("driverId"),
            "constructor_id": row.get("constructorId"),
            "number": row.get("number"),
            "grid": row.get("grid"),
            "position": row.get("position"),
            "position_text": row.get("positionText"),
            "position_order": row.get("positionOrder"),
            "points": row.get("points"),
            "laps": row.get("laps"),
            "time": row.get("time"),
            "milliseconds": row.get("milliseconds"),
            "fastest_lap": row.get("fastestLap"),
            "rank": row.get("rank"),
            "fastest_lap_time": row.get("fastestLapTime"),
            "fastest_lap_speed": row.get("fastestLapSpeed"),
            "status_id": row.get("statusId"),
        }

    @staticmethod
    def f1db_qualifying_result(row: dict) -> dict:
        return {
            "season": row.get("season"),
            "round": row.get("round"),
            "driver_id": row.get("driverId"),
            "constructor_id": row.get("constructorId"),
            "number": row.get("number"),
            "position": row.get("position"),
            "q1": row.get("q1"),
            "q2": row.get("q2"),
            "q3": row.get("q3"),
        }

    @staticmethod
    def f1db_pit_stop(row: dict) -> dict:
        return {
            "season": row.get("season"),
            "round": row.get("round"),
            "driver_id": row.get("driverId"),
            "stop": row.get("stop"),
            "lap": row.get("lap"),
            "time": row.get("time"),
            "duration": row.get("duration"),
        }

    @staticmethod
    def f1db_lap_time(row: dict) -> dict:
        return {
            "season": row.get("season"),
            "round": row.get("round"),
            "driver_id": row.get("driverId"),
            "lap": row.get("lap"),
            "position": row.get("position"),
            "time": row.get("time"),
            "milliseconds": row.get("milliseconds"),
        }

    # --- Jolpica normalization ---

    @staticmethod
    def jolpica_race_result(race: dict) -> dict:
        """Normalize Jolpica race result."""
        results = race.get("Results", [])
        normalized = []
        for result in results:
            driver = result.get("Driver", {})
            constructor = result.get("Constructor", {})
            normalized.append({
                "season": race.get("season"),
                "round": race.get("round"),
                "race_name": race.get("raceName"),
                "date": race.get("date"),
                "circuit": race.get("Circuit", {}).get("circuitName"),
                "driver": {
                    "driver_id": driver.get("driverId"),
                    "code": driver.get("code"),
                    "name": f"{driver.get('givenName')} {driver.get('familyName')}",
                    "nationality": driver.get("nationality"),
                },
                "constructor": {
                    "constructor_id": constructor.get("constructorId"),
                    "name": constructor.get("name"),
                    "nationality": constructor.get("nationality"),
                },
                "number": result.get("number"),
                "grid": result.get("grid"),
                "position": result.get("position"),
                "position_text": result.get("positionText"),
                "position_order": result.get("positionOrder"),
                "points": result.get("points"),
                "laps": result.get("laps"),
                "time": result.get("Time", {}).get("time") if isinstance(result.get("Time"), dict) else result.get("time"),
                "status": result.get("status"),
                "fastest_lap": result.get("FastestLap", {}),
            })
        return normalized

    @staticmethod
    def jolpica_qualifying_result(race: dict) -> list:
        results = race.get("QualifyingResults", [])
        normalized = []
        for result in results:
            driver = result.get("Driver", {})
            constructor = result.get("Constructor", {})
            normalized.append({
                "season": race.get("season"),
                "round": race.get("round"),
                "driver": {
                    "driver_id": driver.get("driverId"),
                    "code": driver.get("code"),
                    "name": f"{driver.get('givenName')} {driver.get('familyName')}",
                },
                "constructor": constructor.get("constructorId"),
                "position": result.get("position"),
                "q1": result.get("Q1"),
                "q2": result.get("Q2"),
                "q3": result.get("Q3"),
            })
        return normalized

    @staticmethod
    def jolpica_lap_time(race: dict) -> list:
        laps = race.get("Laps", [])
        normalized = []
        for lap_group in laps:
            number = lap_group.get("number")
            for lap in lap_group.get("Laps", []):
                timing = lap.get("Timing", {})
                normalized.append({
                    "driver_number": number,
                    "lap": lap.get("lap"),
                    "time": timing.get("time"),
                })
        return normalized

    @staticmethod
    def jolpica_pit_stop(race: dict) -> list:
        pit_stops = race.get("PitStops", [])
        normalized = []
        for stop in pit_stops:
            normalized.append({
                "driver_id": stop.get("driverId"),
                "lap": stop.get("lap"),
                "stop": stop.get("stop"),
                "time": stop.get("time"),
                "duration": stop.get("duration"),
            })
        return normalized

    # --- F1 API normalization ---

    @staticmethod
    def f1api_race_result(race_data: dict) -> list:
        """Normalize f1api.dev race results."""
        results = race_data.get("results", [])
        normalized = []
        for result in results:
            driver = result.get("driver", {})
            team = result.get("team", {})
            normalized.append({
                "season": race_data.get("season"),
                "round": race_data.get("round"),
                "driver": {
                    "driver_id": driver.get("driverId"),
                    "code": driver.get("shortName"),
                    "name": f"{driver.get('name')} {driver.get('surname')}",
                    "number": driver.get("number"),
                },
                "team": {
                    "team_id": team.get("teamId"),
                    "name": team.get("teamName"),
                },
                "position": result.get("position"),
                "points": result.get("points"),
                "grid": result.get("grid"),
                "time": result.get("time"),
                "fastest_lap": result.get("fastLap"),
            })
        return normalized

    @staticmethod
    def f1api_circuit(circuit: dict) -> dict:
        return {
            "circuit_id": circuit.get("circuitId"),
            "name": circuit.get("circuitName"),
            "country": circuit.get("country"),
            "city": circuit.get("city"),
            "length_km": circuit.get("circuitLength"),
            "corners": circuit.get("corners"),
        }

    # --- FastF1 normalization ---

    @staticmethod
    def fastf1_lap(row: Any) -> dict:
        """Convert FastF1 lap row to dict (used by FastF1Adapter)."""
        # Already handled in FastF1Adapter
        pass

    # --- Cross-provider field mapping ---

    FIELD_MAPPING = {
        # F1DB -> Canonical
        "f1db": {
            "race_result": {
                "driverId": "driver_id",
                "constructorId": "constructor_id",
                "positionText": "position_text",
                "positionOrder": "position_order",
                "fastestLap": "fastest_lap",
                "fastestLapTime": "fastest_lap_time",
                "fastestLapSpeed": "fastest_lap_speed",
                "statusId": "status_id",
            },
            "qualifying": {
                "driverId": "driver_id",
                "constructorId": "constructor_id",
            },
            "pit_stop": {
                "driverId": "driver_id",
            },
            "lap_time": {
                "driverId": "driver_id",
            },
        },
        # Jolpica -> Canonical
        "jolpica": {
            "race_result": {
                "driverId": "driver_id",
                "constructorId": "constructor_id",
                "positionText": "position_text",
                "positionOrder": "position_order",
                "fastestLap": "fastest_lap",
            },
            "qualifying": {
                "driverId": "driver_id",
                "constructorId": "constructor_id",
            },
        },
        # F1API -> Canonical
        "f1api": {
            "race_result": {
                "driverId": "driver_id",
                "constructorId": "constructor_id",
            },
        },
    }

    @classmethod
    def map_fields(cls, provider: str, entity: str, data: dict) -> dict:
        """Map provider-specific field names to canonical names."""
        mapping = cls.FIELD_MAPPING.get(provider, {}).get(entity, {})
        return {mapping.get(k, k): v for k, v in data.items()}


class DataQualityChecker:
    """Validates canonical data for quality issues."""

    @staticmethod
    def check_race_result(result: dict) -> list[str]:
        """Check race result for quality issues."""
        errors = []
        if result.get("position") is None:
            errors.append("Missing position")
        if result.get("driver_id") is None:
            errors.append("Missing driver_id")
        if result.get("laps") is not None and result["laps"] < 0:
            errors.append("Invalid laps (negative)")
        if result.get("position") and result["position"] < 1:
            errors.append("Invalid position (less than 1)")
        return errors

    @staticmethod
    def check_lap(lap: dict) -> list[str]:
        errors = []
        if lap.get("lap_number") is None:
            errors.append("Missing lap_number")
        if lap.get("lap_time_s") is not None and lap["lap_time_s"] <= 0:
            errors.append("Invalid lap_time_s (non-positive)")
        if lap.get("lap_number") and lap["lap_number"] < 1:
            errors.append("Invalid lap_number (less than 1)")
        return errors

    @staticmethod
    def check_pit_stop(stop: dict) -> list[str]:
        errors = []
        if stop.get("pit_in_lap") is None:
            errors.append("Missing pit_in_lap")
        if stop.get("driver") is None:
            errors.append("Missing driver")
        return errors


def validate_canonical_data(data: dict, entity_type: str) -> dict:
    """Validate canonical data and return validation results."""
    checker = DataQualityChecker()
    errors = []
    warnings = []

    if entity_type == "race_result":
        for result in data.get("results", []):
            errors.extend(checker.check_race_result(result))
    elif entity_type == "lap":
        for lap in data.get("laps", []):
            errors.extend(checker.check_lap(lap))
    elif entity_type == "pit_stop":
        for stop in data.get("pit_stops", []):
            errors.extend(checker.check_pit_stop(stop))

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "checked_count": len(data.get("results", data.get("laps", data.get("pit_stops", [])))),
    }