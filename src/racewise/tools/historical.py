"""Historical session tools: deterministic tools over the F1DB canonical store.

These tools expose the canonical historical data (results, qualifying, pit
stops, fastest laps, session catalog) through the same contracted Tool
boundary as the FastF1 tools, so MCP/host agents can investigate any era
with explicit AVAILABLE / UNAVAILABLE provenance.
"""
from __future__ import annotations

from typing import Any

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.tools.contract import Tool, ToolError, ToolRegistry, ToolSpec
from racewise.tools.implementations import build_default_registry

HISTORY_TOOLS_VERSION = "1.0.0"

_AVAILABILITY_NOTE = (
    "Availability is data-derived: UNAVAILABLE means the canonical store has "
    "no rows for this capability from this provider, not that it is zero."
)


def _spec(
    name: str,
    description: str,
    properties: dict,
    required: list[str],
    output_schema: dict,
    limitations: list[str] | None = None,
) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        input_schema={"type": "object", "properties": properties, "required": required},
        output_schema=output_schema,
        version=HISTORY_TOOLS_VERSION,
        limitations=limitations or [],
    )


SEASON_PARAM = {"type": "integer", "description": "Season year, e.g. 1950"}
ROUND_PARAM = {"type": "integer", "description": "Round number within the season, 1-based"}
SESSION_TYPE_PARAM = {
    "type": "string",
    "description": (
        "Session type: RACE, QUALIFYING, SPRINT, SPRINT_QUALIFYING, "
        "FREE_PRACTICE_1..4, QUALIFYING_1, QUALIFYING_2, PRE_QUALIFYING, WARMING_UP"
    ),
}


class GetHistoricalSessionTool(Tool):
    """Resolve a historical session and its data-derived availability."""

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self.spec = _spec(
            "get_historical_session",
            "Resolve a historical session by season/round/type; returns race metadata, "
            "session identity, source provenance, and data-derived availability flags.",
            {"season": SEASON_PARAM, "round": ROUND_PARAM, "session_type": SESSION_TYPE_PARAM},
            ["season", "round"],
            {
                "type": "object",
                "properties": {
                    "found": {"type": "boolean"},
                    "session_id": {"type": ["string", "null"]},
                    "race_name": {"type": ["string", "null"]},
                    "date": {"type": ["string", "null"]},
                    "circuit": {"type": ["string", "null"]},
                    "sessions_present": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                    },
                    "availability": {
                        "type": ["object", "null"],
                        "additionalProperties": {"type": ["string", "integer", "null"]},
                    },
                    "source_provider": {"type": ["string", "null"]},
                    "source_version": {"type": ["string", "null"]},
                },
                "required": ["found", "session_id", "race_name", "date", "circuit",
                             "sessions_present", "availability", "source_provider", "source_version"],
            },
            [_AVAILABILITY_NOTE],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        season = int(kwargs["season"])
        round_num = int(kwargs["round"])
        session_type = str(kwargs.get("session_type", "RACE")).upper()
        session = self._queries.resolve_session(season, round_num, session_type)
        race = session["race"] if session else self._queries.resolve_race(season, round_num=round_num)
        present = [s["session_type"] for s in self._queries.list_race_sessions(season, round_num)]
        availability = self._queries.get_availability(season, round_num, session_type)
        if availability is not None:
            availability = {
                k: v
                for k, v in availability.items()
                if k.endswith("_count") or k.endswith("_availability")
            }
        if session is None:
            return {
                "found": False,
                "session_id": None,
                "race_name": race["official_name"] if race else None,
                "date": race["date"] if race else None,
                "circuit": race["circuit_name"] if race else None,
                "sessions_present": present,
                "availability": availability,
                "source_provider": "f1db" if race else None,
                "source_version": None,
            }
        return {
            "found": True,
            "session_id": session["session_id"],
            "race_name": race["official_name"] if race else None,
            "date": session["date_start"] or (race["date"] if race else None),
            "circuit": race["circuit_name"] if race else None,
            "sessions_present": present,
            "availability": availability,
            "source_provider": session["source_provider"],
            "source_version": session["source_version"],
        }


class GetHistoricalResultsTool(Tool):
    """Canonical classification for a historical session."""

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self.spec = _spec(
            "get_historical_results",
            "Return the canonical classification for a historical race/sprint session: "
            "position, driver, constructor, grid, status, points, time. Empty list means "
            "UNAVAILABLE (no canonical rows), never a zero-result session.",
            {"season": SEASON_PARAM, "round": ROUND_PARAM, "session_type": SESSION_TYPE_PARAM},
            ["season", "round"],
            {
                "type": "object",
                "properties": {
                    "season": {"type": "integer"},
                    "round": {"type": "integer"},
                    "session_type": {"type": "string"},
                    "n_results": {"type": "integer"},
                    "available": {"type": "boolean"},
                    "source_provider": {"type": ["string", "null"]},
                    "results": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "position": {"type": ["integer", "null"]},
                                "position_text": {"type": ["string", "null"]},
                                "driver": {"type": "string"},
                                "driver_key": {"type": "string"},
                                "constructor": {"type": ["string", "null"]},
                                "grid": {"type": ["integer", "null"]},
                                "points": {"type": ["number", "null"]},
                                "laps": {"type": ["integer", "null"]},
                                "time": {"type": ["string", "null"]},
                                "time_millis": {"type": ["integer", "null"]},
                                "status": {"type": ["string", "null"]},
                            },
                            "required": ["position", "position_text", "driver", "driver_key",
                                         "constructor", "grid", "points", "laps", "time",
                                         "time_millis", "status"],
                        },
                    },
                },
                "required": ["season", "round", "session_type", "n_results", "available",
                             "source_provider", "results"],
            },
            ["Classification is as recorded by the source; shared cars appear as separate rows."],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        season = int(kwargs["season"])
        round_num = int(kwargs["round"])
        session_type = str(kwargs.get("session_type", "RACE")).upper()
        rows = self._queries.get_results(season, round_num, session_type)
        return {
            "season": season,
            "round": round_num,
            "session_type": session_type,
            "n_results": len(rows),
            "available": len(rows) > 0,
            "source_provider": "f1db",
            "results": [
                {
                    "position": r.get("position"),
                    "position_text": r.get("position_text"),
                    "driver": r.get("driver_name"),
                    "driver_key": r.get("driver_key") or r.get("driver_code"),
                    "constructor": r.get("constructor_name"),
                    "grid": r.get("grid"),
                    "points": r.get("points"),
                    "laps": r.get("laps"),
                    "time": r.get("time"),
                    "time_millis": r.get("milliseconds"),
                    "status": r.get("status"),
                }
                for r in rows
            ],
        }


class GetHistoricalQualifyingTool(Tool):
    """Canonical qualifying/practice classification for a historical session."""

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self.spec = _spec(
            "get_historical_qualifying",
            "Return canonical qualifying (or practice/grid) rows for a historical session, "
            "preserving the source's Q1/Q2/Q3 representation. Historical eras with a single "
            "session carry q1 only; q2/q3 are null, not fabricated.",
            {"season": SEASON_PARAM, "round": ROUND_PARAM, "session_type": SESSION_TYPE_PARAM},
            ["season", "round"],
            {
                "type": "object",
                "properties": {
                    "season": {"type": "integer"},
                    "round": {"type": "integer"},
                    "session_type": {"type": "string"},
                    "n_rows": {"type": "integer"},
                    "available": {"type": "boolean"},
                    "source_provider": {"type": ["string", "null"]},
                    "rows": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "position": {"type": ["integer", "null"]},
                                "driver": {"type": "string"},
                                "driver_key": {"type": "string"},
                                "constructor": {"type": ["string", "null"]},
                                "q1": {"type": ["string", "null"]},
                                "q2": {"type": ["string", "null"]},
                                "q3": {"type": ["string", "null"]},
                                "position_text": {"type": ["string", "null"]},
                            },
                            "required": ["position", "driver", "driver_key", "constructor",
                                         "q1", "q2", "q3", "position_text"],
                        },
                    },
                },
                "required": ["season", "round", "session_type", "n_rows", "available",
                             "source_provider", "rows"],
            },
            ["Only rows the source actually provides are returned."],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        season = int(kwargs["season"])
        round_num = int(kwargs["round"])
        session_type = str(kwargs.get("session_type", "QUALIFYING")).upper()
        rows = self._queries.get_qualifying(season, round_num, session_type)
        return {
            "season": season,
            "round": round_num,
            "session_type": session_type,
            "n_rows": len(rows),
            "available": len(rows) > 0,
            "source_provider": "f1db",
            "rows": [
                {
                    "position": r.get("position"),
                    "driver": r.get("driver_name"),
                    "driver_key": r.get("driver_key") or r.get("driver_code"),
                    "constructor": r.get("constructor_name"),
                    "q1": r.get("q1"),
                    "q2": r.get("q2"),
                    "q3": r.get("q3"),
                    "position_text": r.get("position_text"),
                }
                for r in rows
            ],
        }


class GetHistoricalPitStopsTool(Tool):
    """Canonical pit stops for a historical race."""

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self.spec = _spec(
            "get_historical_pit_stops",
            "Return canonical pit stops for a historical race session: driver, lap, stop "
            "number, duration. Empty list means pit-stop data is UNAVAILABLE for the era; "
            "it does NOT mean zero stops occurred.",
            {
                "season": SEASON_PARAM,
                "round": ROUND_PARAM,
                "session_type": SESSION_TYPE_PARAM,
                "driver_key": {"type": "string", "description": "Optional F1DB driver key filter"},
            },
            ["season", "round"],
            {
                "type": "object",
                "properties": {
                    "season": {"type": "integer"},
                    "round": {"type": "integer"},
                    "session_type": {"type": "string"},
                    "n_stops": {"type": "integer"},
                    "available": {"type": "boolean"},
                    "source_provider": {"type": ["string", "null"]},
                    "stops": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "driver": {"type": "string"},
                                "driver_key": {"type": "string"},
                                "lap": {"type": "integer"},
                                "stop_number": {"type": ["integer", "null"]},
                                "duration_s": {"type": ["number", "null"]},
                            },
                            "required": ["driver", "driver_key", "lap", "stop_number", "duration_s"],
                        },
                    },
                },
                "required": ["season", "round", "session_type", "n_stops", "available",
                             "source_provider", "stops"],
            },
            [
                "NO DATA != ZERO STOPS: an empty result must be reported as UNAVAILABLE.",
                "Tyre compounds are not recorded by this source.",
            ],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        season = int(kwargs["season"])
        round_num = int(kwargs["round"])
        session_type = str(kwargs.get("session_type", "RACE")).upper()
        driver_key = kwargs.get("driver_key")
        rows = self._queries.get_pit_stops(season, round_num, session_type, driver_key)
        return {
            "season": season,
            "round": round_num,
            "session_type": session_type,
            "n_stops": len(rows),
            "available": len(rows) > 0,
            "source_provider": "f1db",
            "stops": [
                {
                    "driver": r.get("driver_name"),
                    "driver_key": r.get("driver_key"),
                    "lap": r.get("lap"),
                    "stop_number": r.get("stop_number"),
                    "duration_s": r.get("duration"),
                }
                for r in rows
            ],
        }


class GetHistoricalFastestLapsTool(Tool):
    """Fastest-lap records (the only lap-level data this source provides)."""

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self.spec = _spec(
            "get_historical_fastest_laps",
            "Return fastest-lap records for a historical race session. This is the only "
            "lap-level data the source provides - NOT complete lap telemetry.",
            {
                "season": SEASON_PARAM,
                "round": ROUND_PARAM,
                "session_type": SESSION_TYPE_PARAM,
                "driver_key": {"type": "string", "description": "Optional F1DB driver key filter"},
            },
            ["season", "round"],
            {
                "type": "object",
                "properties": {
                    "season": {"type": "integer"},
                    "round": {"type": "integer"},
                    "session_type": {"type": "string"},
                    "n_records": {"type": "integer"},
                    "available": {"type": "boolean"},
                    "full_telemetry_available": {"type": "boolean"},
                    "source_provider": {"type": ["string", "null"]},
                    "laps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "driver": {"type": "string"},
                                "driver_key": {"type": "string"},
                                "lap_number": {"type": "integer"},
                                "time_s": {"type": ["number", "null"]},
                            },
                            "required": ["driver", "driver_key", "lap_number", "time_s"],
                        },
                    },
                },
                "required": ["season", "round", "session_type", "n_records", "available",
                             "full_telemetry_available", "source_provider", "laps"],
            },
            ["full_telemetry_available is always false for this provider; use FastF1 for complete laps."],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        season = int(kwargs["season"])
        round_num = int(kwargs["round"])
        session_type = str(kwargs.get("session_type", "RACE")).upper()
        driver_key = kwargs.get("driver_key")
        rows = self._queries.get_lap_times(season, round_num, session_type, driver_key)
        return {
            "season": season,
            "round": round_num,
            "session_type": session_type,
            "n_records": len(rows),
            "available": len(rows) > 0,
            "full_telemetry_available": False,
            "source_provider": "f1db",
            "laps": [
                {
                    "driver": r.get("driver_name"),
                    "driver_key": r.get("driver_key"),
                    "lap_number": r.get("lap_number"),
                    "time_s": r.get("time_s"),
                }
                for r in rows
            ],
        }


class SearchHistoricalCatalogTool(Tool):
    """Search the canonical session catalog."""

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self.spec = _spec(
            "search_historical_catalog",
            "Search the historical session catalog: which races/sessions exist per season "
            "and what capabilities are data-derived as AVAILABLE.",
            {
                "season": {"type": "integer", "description": "Optional season filter"},
                "session_type": {"type": "string", "description": "Optional session type filter"},
                "availability": {
                    "type": "string",
                    "description": "Optional filter: AVAILABLE or UNAVAILABLE (results-based)",
                },
                "limit": {"type": "integer", "description": "Max rows (default 25, max 200)"},
            },
            [],
            {
                "type": "object",
                "properties": {
                    "n_entries": {"type": "integer"},
                    "entries": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "season": {"type": "integer"},
                                "round": {"type": "integer"},
                                "race_name": {"type": ["string", "null"]},
                                "date": {"type": ["string", "null"]},
                                "session_type": {"type": "string"},
                                "results_count": {"type": "integer"},
                                "qualifying_count": {"type": "integer"},
                                "pit_stops_count": {"type": "integer"},
                                "laps_count": {"type": "integer"},
                            },
                            "required": ["season", "round", "race_name", "date", "session_type",
                                         "results_count", "qualifying_count", "pit_stops_count",
                                         "laps_count"],
                        },
                    },
                },
                "required": ["n_entries", "entries"],
            },
            ["Counts reflect actual canonical rows per session."],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        limit = min(int(kwargs.get("limit", 25)), 200)
        rows = self._queries.catalog_search(
            season=kwargs.get("season"),
            session_type=kwargs.get("session_type"),
            availability=kwargs.get("availability"),
            limit=limit,
        )
        return {
            "n_entries": len(rows),
            "entries": [
                {
                    "season": r["season"],
                    "round": r["round"],
                    "race_name": r.get("race_name"),
                    "date": r.get("date"),
                    "session_type": r["session_type"],
                    "results_count": r["results_count"],
                    "qualifying_count": r["qualifying_count"],
                    "pit_stops_count": r["pit_stops_count"],
                    "laps_count": r["laps_count"],
                }
                for r in rows
            ],
        }


def build_historical_registry(queries: CanonicalQueries) -> ToolRegistry:
    """Registry of canonical historical tools (composable with the FastF1 tools)."""
    registry = ToolRegistry()
    for tool in (
        GetHistoricalSessionTool(queries),
        GetHistoricalResultsTool(queries),
        GetHistoricalQualifyingTool(queries),
        GetHistoricalPitStopsTool(queries),
        GetHistoricalFastestLapsTool(queries),
        SearchHistoricalCatalogTool(queries),
    ):
        registry.register(tool)
    return registry


def build_full_registry(context: Any, queries: CanonicalQueries) -> ToolRegistry:
    """FastF1 session tools + canonical historical tools in one registry."""
    registry = build_default_registry(context)
    historical = build_historical_registry(queries)
    for name, tool in historical._tools.items():
        registry.register(tool)
    return registry
