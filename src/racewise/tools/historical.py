"""Historical session tools: deterministic tools over the F1DB canonical store.

These tools expose the canonical historical data (results, qualifying, pit
stops, fastest laps, session catalog) through the same contracted Tool
boundary as the FastF1 tools, so MCP/host agents can investigate any era
with explicit AVAILABLE / UNAVAILABLE provenance.
"""
from __future__ import annotations

from typing import Any

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.data.historical.telemetry_analysis import compare_telemetry_lap
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


class GetHistoricalStintsTool(Tool):
    """Canonical tyre stints (FastF1 provider, modern sessions)."""

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self.spec = _spec(
            "get_historical_stints",
            "Return canonical tyre stints for a session (compound, lap range, count). "
            "Sourced from FastF1 where ingested; empty list means UNAVAILABLE for this "
            "session, never 'no stints occurred'.",
            {"season": SEASON_PARAM, "round": ROUND_PARAM, "session_type": SESSION_TYPE_PARAM,
             "driver_key": {"type": "string", "description": "Optional driver code filter (e.g. VER)"}},
            ["season", "round"],
            {
                "type": "object",
                "properties": {
                    "season": {"type": "integer"},
                    "round": {"type": "integer"},
                    "session_type": {"type": "string"},
                    "n_stints": {"type": "integer"},
                    "available": {"type": "boolean"},
                    "source_provider": {"type": ["string", "null"]},
                    "stints": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "driver": {"type": "string"},
                                "driver_key": {"type": "string"},
                                "stint_number": {"type": "integer"},
                                "compound": {"type": ["string", "null"]},
                                "lap_start": {"type": "integer"},
                                "lap_end": {"type": "integer"},
                                "lap_count": {"type": "integer"},
                            },
                            "required": ["driver", "driver_key", "stint_number", "compound",
                                         "lap_start", "lap_end", "lap_count"],
                        },
                    },
                },
                "required": ["season", "round", "session_type", "n_stints", "available",
                             "source_provider", "stints"],
            },
            ["Compound is recorded by FastF1 only for sessions it covers (2018+); '|' marks mixed sets."],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        season = int(kwargs["season"])
        round_num = int(kwargs["round"])
        session_type = str(kwargs.get("session_type", "RACE")).upper()
        driver_key = kwargs.get("driver_key")
        rows = self._queries.get_stints(season, round_num, session_type, driver_key)
        providers = sorted({r.get("source_provider") for r in rows if r.get("source_provider")})
        return {
            "season": season,
            "round": round_num,
            "session_type": session_type,
            "n_stints": len(rows),
            "available": len(rows) > 0,
            "source_provider": providers[0] if len(providers) == 1 else ("|".join(providers) if providers else None),
            "stints": [
                {
                    "driver": r.get("driver_name"),
                    "driver_key": r.get("driver_key"),
                    "stint_number": r.get("stint_number"),
                    "compound": r.get("compound"),
                    "lap_start": r.get("lap_start"),
                    "lap_end": r.get("lap_end"),
                    "lap_count": r.get("lap_count"),
                }
                for r in rows
            ],
        }


class GetHistoricalWeatherTool(Tool):
    """Canonical weather observations (FastF1 provider)."""

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self.spec = _spec(
            "get_historical_weather",
            "Return canonical weather observations for a session (air/track temp, humidity, "
            "rainfall, wind, pressure) at native source precision. No interpolation: gaps "
            "between observations remain gaps.",
            {"season": SEASON_PARAM, "round": ROUND_PARAM, "session_type": SESSION_TYPE_PARAM},
            ["season", "round"],
            {
                "type": "object",
                "properties": {
                    "season": {"type": "integer"},
                    "round": {"type": "integer"},
                    "session_type": {"type": "string"},
                    "n_observations": {"type": "integer"},
                    "available": {"type": "boolean"},
                    "source_provider": {"type": ["string", "null"]},
                    "observations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "timestamp": {"type": ["string", "null"]},
                                "air_temp_c": {"type": ["number", "null"]},
                                "track_temp_c": {"type": ["number", "null"]},
                                "humidity": {"type": ["number", "null"]},
                                "rainfall": {"type": ["boolean", "null"]},
                                "wind_direction": {"type": ["integer", "null"]},
                                "wind_speed": {"type": ["number", "null"]},
                                "pressure": {"type": ["number", "null"]},
                            },
                            "required": ["timestamp", "air_temp_c", "track_temp_c", "humidity",
                                         "rainfall", "wind_direction", "wind_speed", "pressure"],
                        },
                    },
                },
                "required": ["season", "round", "session_type", "n_observations", "available",
                             "source_provider", "observations"],
            },
            ["Weather is available only where the provider recorded it; UNAVAILABLE means no data."],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        season = int(kwargs["season"])
        round_num = int(kwargs["round"])
        session_type = str(kwargs.get("session_type", "RACE")).upper()
        rows = self._queries.get_weather(season, round_num, session_type)
        providers = sorted({r.get("source_provider") for r in rows if r.get("source_provider")})
        return {
            "season": season,
            "round": round_num,
            "session_type": session_type,
            "n_observations": len(rows),
            "available": len(rows) > 0,
            "source_provider": providers[0] if len(providers) == 1 else ("|".join(providers) if providers else None),
            "observations": [
                {
                    "timestamp": r.get("timestamp"),
                    "air_temp_c": r.get("air_temp_c"),
                    "track_temp_c": r.get("track_temp_c"),
                    "humidity": r.get("humidity"),
                    "rainfall": (
                        bool(r["rainfall"]) if r.get("rainfall") is not None else None
                    ),
                    "wind_direction": r.get("wind_direction"),
                    "wind_speed": r.get("wind_speed"),
                    "pressure": r.get("pressure"),
                }
                for r in rows
            ],
        }


class GetHistoricalRaceControlTool(Tool):
    """Canonical race-control events (FastF1 provider)."""

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self.spec = _spec(
            "get_historical_race_control",
            "Return canonical race-control events for a session (flags, safety car, "
            "penalties, track status messages) in chronological order.",
            {"season": SEASON_PARAM, "round": ROUND_PARAM, "session_type": SESSION_TYPE_PARAM},
            ["season", "round"],
            {
                "type": "object",
                "properties": {
                    "season": {"type": "integer"},
                    "round": {"type": "integer"},
                    "session_type": {"type": "string"},
                    "n_events": {"type": "integer"},
                    "available": {"type": "boolean"},
                    "source_provider": {"type": ["string", "null"]},
                    "events": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "timestamp": {"type": ["string", "null"]},
                                "category": {"type": ["string", "null"]},
                                "message": {"type": ["string", "null"]},
                                "lap": {"type": ["integer", "null"]},
                            },
                            "required": ["timestamp", "category", "message", "lap"],
                        },
                    },
                },
                "required": ["season", "round", "session_type", "n_events", "available",
                             "source_provider", "events"],
            },
            ["Messages are preserved verbatim from the source; flag/scope detail is inside the message text."],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        season = int(kwargs["season"])
        round_num = int(kwargs["round"])
        session_type = str(kwargs.get("session_type", "RACE")).upper()
        rows = self._queries.get_race_control(season, round_num, session_type)
        providers = sorted({r.get("source_provider") for r in rows if r.get("source_provider")})
        return {
            "season": season,
            "round": round_num,
            "session_type": session_type,
            "n_events": len(rows),
            "available": len(rows) > 0,
            "source_provider": providers[0] if len(providers) == 1 else ("|".join(providers) if providers else None),
            "events": [
                {
                    "timestamp": r.get("timestamp"),
                    "category": r.get("category"),
                    "message": r.get("message"),
                    "lap": r.get("lap"),
                }
                for r in rows
            ],
        }



_DRIVER_ALIASES = {
    # Historical 3-letter codes collide across eras; telemetry driver identity
    # is season-scoped. Accept either a driver_key slug or a code and resolve
    # through the canonical store (never guess).
}


def _normalize_driver_key(
    queries: CanonicalQueries,
    raw: str,
    season: int | None = None,
    round_num: int | None = None,
    session_type: str | None = None,
) -> str:
    """Resolve a driver reference (slug or code) to a canonical driver_key.

    Slugs are unambiguous and resolve directly. Three-letter codes collide
    across eras (190 codes are shared by multiple drivers historically), so a
    code is only accepted when it resolves to exactly one participant of the
    requested session - season-scoped identity, never a global guess.
    """
    key = str(raw).strip()
    if not key:
        raise ToolError("driver reference is empty", code="invalid_input", field="driver_key")
    slug = key.lower().replace(" ", "-")
    with queries._conn() as conn:
        row = conn.execute(
            "SELECT driver_key FROM canonical_drivers WHERE driver_key = ? LIMIT 1", (slug,)
        ).fetchone()
        if row:
            return row[0]
        if season is None:
            return slug
        session = queries.resolve_session(int(season), int(round_num), session_type or "RACE")
        if session is None:
            return slug
        matches = conn.execute(
            """
            SELECT DISTINCT d.driver_key
            FROM canonical_results r
            JOIN canonical_drivers d ON d.driver_id = r.driver_id
            WHERE r.session_id = ? AND UPPER(d.code) = UPPER(?)
            """,
            (session["session_id"], key),
        ).fetchall()
    if len(matches) == 1:
        return matches[0][0]
    return slug


class GetTelemetrySummaryTool(Tool):
    """Count-derived telemetry availability for a session (bounded output)."""

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self.spec = _spec(
            "get_historical_telemetry_summary",
            "Telemetry availability for a session, derived from actual canonical_telemetry "
            "row counts (FastF1 provider, bounded ingestion only). Returns sample count, "
            "driver count, and the ingested lap numbers. available=false means no telemetry "
            "rows exist - never assume telemetry by season.",
            {"season": SEASON_PARAM, "round": ROUND_PARAM, "session_type": SESSION_TYPE_PARAM},
            ["season", "round"],
            {
                "type": "object",
                "properties": {
                    "season": {"type": "integer"},
                    "round": {"type": "integer"},
                    "session_type": {"type": "string"},
                    "available": {"type": "boolean"},
                    "sample_count": {"type": "integer"},
                    "drivers": {"type": "integer"},
                    "laps": {"type": "array", "items": {"type": "integer"}},
                    "source_provider": {"type": ["string", "null"]},
                },
                "required": ["season", "round", "session_type", "available", "sample_count",
                             "drivers", "laps", "source_provider"],
            },
            [
                "Telemetry is ingested for a bounded benchmark set only; absence means "
                "UNAVAILABLE, not zero laps driven.",
                _AVAILABILITY_NOTE,
            ],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        season = int(kwargs["season"])
        round_num = int(kwargs["round"])
        session_type = str(kwargs.get("session_type", "RACE")).upper()
        summary = self._queries.telemetry_summary(season, round_num, session_type)
        return {
            "season": season,
            "round": round_num,
            "session_type": session_type,
            "available": bool(summary["available"]),
            "sample_count": int(summary["sample_count"]),
            "drivers": int(summary["drivers"]),
            "laps": [int(l) for l in summary["laps"]],
            "source_provider": "fastf1" if summary["available"] else None,
        }


class GetLapTelemetryTool(Tool):
    """Bounded telemetry samples for one driver-lap (hard output cap)."""

    _SIGNALS = ("speed", "throttle", "brake", "gear", "rpm", "drs")

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self.spec = _spec(
            "get_historical_lap_telemetry",
            "Return bounded telemetry samples for one driver-lap (default signals: speed, "
            "throttle, brake; optional gear/rpm/drs). lap_time_s is lap-relative seconds, "
            "time_elapsed_s is session-relative; native FastF1 resolution, no interpolation. "
            "Requests are hard-capped (max_samples <= 2000); unbounded dumps are rejected.",
            {
                "season": SEASON_PARAM, "round": ROUND_PARAM,
                "session_type": SESSION_TYPE_PARAM,
                "driver_key": {"type": "string", "description": "Driver code, e.g. VER"},
                "lap_number": {"type": "integer", "description": "Lap number within the session"},
                "signals": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(self._SIGNALS)},
                    "description": "Optional signal whitelist (default speed/throttle/brake)",
                },
                "max_samples": {
                    "type": "integer",
                    "minimum": 1, "maximum": 2000,
                    "description": "Hard output cap; server clamps to 2000",
                },
            },
            ["season", "round", "driver_key", "lap_number"],
            {
                "type": "object",
                "properties": {
                    "season": {"type": "integer"},
                    "round": {"type": "integer"},
                    "session_type": {"type": "string"},
                    "driver_key": {"type": "string"},
                    "lap_number": {"type": "integer"},
                    "available": {"type": "boolean"},
                    "n_samples": {"type": "integer"},
                    "truncated": {"type": "boolean"},
                    "signals": {"type": "array", "items": {"type": "string"}},
                    "samples": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "lap_time_s": {"type": ["number", "null"]},
                                "time_elapsed_s": {"type": ["number", "null"]},
                                "signal": {"type": "string"},
                                "value": {"type": ["number", "boolean"]},
                                "source_provider": {"type": ["string", "null"]},
                            },
                            "required": ["lap_time_s", "signal", "value"],
                        },
                    },
                },
                "required": ["season", "round", "session_type", "driver_key", "lap_number",
                             "available", "n_samples", "truncated", "signals", "samples"],
            },
            [
                "UNAVAILABLE (empty samples) means no telemetry rows for this driver-lap; "
                "identity-unresolved drivers were skipped at ingestion, never guessed.",
                "Output is hard-bounded to protect agent context; use windows instead of "
                "requesting full sessions.",
            ],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        season = int(kwargs["season"])
        round_num = int(kwargs["round"])
        session_type = str(kwargs.get("session_type", "RACE")).upper()
        season = int(kwargs["season"])
        round_num = int(kwargs["round"])
        session_type = str(kwargs.get("session_type", "RACE")).upper()
        driver_key = _normalize_driver_key(
            self._queries, str(kwargs["driver_key"]), season, round_num, session_type
        )
        lap_number = int(kwargs["lap_number"])
        signals = kwargs.get("signals")
        if signals is not None:
            signals = [str(s).lower() for s in signals]
            bad = [s for s in signals if s not in self._SIGNALS]
            if bad:
                raise ToolError(
                    f"unknown telemetry signals: {bad}", code="invalid_input",
                    field="signals",
                )
        max_samples = min(int(kwargs.get("max_samples", 2000)), 2000)
        try:
            rows = self._queries.get_lap_telemetry(
                season, round_num, driver_key, lap_number,
                session_type=session_type, signals=signals, max_samples=max_samples,
            )
        except ValueError as exc:  # query-layer bound enforcement
            raise ToolError(str(exc), code="invalid_input") from exc
        requested = signals or ["speed", "throttle", "brake"]
        return {
            "season": season, "round": round_num, "session_type": session_type,
            "driver_key": driver_key, "lap_number": lap_number,
            "available": len(rows) > 0,
            "n_samples": len(rows),
            "truncated": len(rows) >= min(max_samples, 2000),
            "signals": requested,
            "samples": [
                {
                    "lap_time_s": r.get("lap_time_s"),
                    "time_elapsed_s": r.get("time_elapsed_s"),
                    "signal": r["signal"],
                    "value": r["value"],
                    "source_provider": r.get("source_provider"),
                }
                for r in rows
            ],
        }


class CompareTelemetryLapTool(Tool):
    """Deterministic two-driver lap telemetry comparison (windowed time-loss)."""

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self.spec = _spec(
            "compare_historical_telemetry_lap",
            "Compare two drivers over one lap using canonical telemetry: per-window speed "
            "delta with an estimated straight-line time loss, plus throttle/brake association "
            "in the highest-loss window. Deterministic; returns INSUFFICIENT_EVIDENCE when "
            "telemetry is missing for either driver-lap. The numbers come from SQL over "
            "canonical_telemetry, not from narration.",
            {
                "season": SEASON_PARAM, "round": ROUND_PARAM,
                "session_type": SESSION_TYPE_PARAM,
                "driver_a": {"type": "string", "description": "Reference driver code, e.g. VER"},
                "driver_b": {"type": "string", "description": "Comparison driver code, e.g. PER"},
                "lap_number": {"type": "integer"},
                "window_s": {
                    "type": "number", "minimum": 1.0, "maximum": 30.0,
                    "description": "Window width in seconds (default 5)",
                },
            },
            ["season", "round", "driver_a", "driver_b", "lap_number"],
            {
                "type": "object",
                "additionalProperties": True,
                "required": ["verdict"],
            },
            [
                "The time-loss figure is a straight-line estimate (1 - v_B/v_A per window); "
                "treat as an approximation, never as measured reality.",
                "Throttle/brake deltas are associations, not proven causation.",
            ],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        return compare_telemetry_lap(
            self._queries,
            season=int(kwargs["season"]),
            round_num=int(kwargs["round"]),
            driver_a=_normalize_driver_key(
                self._queries, str(kwargs["driver_a"]),
                int(kwargs["season"]), int(kwargs["round"]),
                str(kwargs.get("session_type", "RACE")).upper(),
            ),
            driver_b=_normalize_driver_key(
                self._queries, str(kwargs["driver_b"]),
                int(kwargs["season"]), int(kwargs["round"]),
                str(kwargs.get("session_type", "RACE")).upper(),
            ),
            lap_number=int(kwargs["lap_number"]),
            window_s=float(kwargs.get("window_s", 5.0)),
            session_type=str(kwargs.get("session_type", "RACE")).upper(),
        )


class AttributeLapLossTool(Tool):
    """Deterministic lap-loss attribution: measured delta -> region/sector
    decomposition with an explicit residual and falsification checks."""

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self.spec = _spec(
            "attribute_historical_lap_loss",
            "Attribute a measured lap-time delta (driver B vs driver A) to lap-time regions "
            "and canonical sectors: observed delta (fact), per-region speed-trace loss "
            "estimate, sector deltas summing exactly to the delta, explicit residual with "
            "reconciliation verdict, per-signal metrics, and falsification checks for "
            "alternative explanations. Deterministic; UNAVAILABLE/INSUFFICIENT_EVIDENCE "
            "when telemetry, laps or context are missing - never a guessed attribution.",
            {
                "season": SEASON_PARAM, "round": ROUND_PARAM,
                "session_type": SESSION_TYPE_PARAM,
                "driver_a": {"type": "string", "description": "Reference driver key, e.g. max-verstappen"},
                "driver_b": {"type": "string", "description": "Comparison driver key, e.g. sergio-perez"},
                "lap_number": {"type": "integer", "minimum": 1},
                "region_s": {"type": "number", "minimum": 5.0, "maximum": 30.0,
                             "description": "Attribution region width in seconds (default 15)"},
                "include_falsification": {"type": "boolean",
                                          "description": "Attach alternative-explanation checks (default true)"},
            },
            ["season", "round", "driver_a", "driver_b", "lap_number"],
            {"type": "object", "additionalProperties": True, "required": ["status"]},
            [
                "Region losses are speed-trace estimates (straight-line model), not causal "
                "contributions; the residual vs the measured delta is reported explicitly.",
                "Sector deltas are measured facts (canonical sector splits) and sum to the "
                "observed delta; telemetry estimates inside sectors are model output.",
                "Bounded: one lap, fixed region grid, no raw-sample dumps.",
            ],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        from racewise.data.historical.loss_attribution import attribute_lap_loss, falsify_attribution

        att = attribute_lap_loss(
            self._queries,
            season=int(kwargs["season"]),
            round_num=int(kwargs["round"]),
            driver_a=_normalize_driver_key(
                self._queries, str(kwargs["driver_a"]),
                int(kwargs["season"]), int(kwargs["round"]),
                str(kwargs.get("session_type", "RACE")).upper(),
            ),
            driver_b=_normalize_driver_key(
                self._queries, str(kwargs["driver_b"]),
                int(kwargs["season"]), int(kwargs["round"]),
                str(kwargs.get("session_type", "RACE")).upper(),
            ),
            lap_number=int(kwargs["lap_number"]),
            session_type=str(kwargs.get("session_type", "RACE")).upper(),
            region_s=float(kwargs.get("region_s", 15.0)),
        )
        if kwargs.get("include_falsification", True) and att.get("status") in (
            "VALID_COMPARISON", "VALID_WITH_CAVEATS"
        ):
            att["falsification"] = falsify_attribution(self._queries, att)
        return att


class AttributeStintLossTool(Tool):
    """Stint-level attribution: aggregated per-lap attribution across a stint."""

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self.spec = _spec(
            "attribute_historical_stint_loss",
            "Aggregate lap-loss attribution across one stint for two drivers: per-lap "
            "observed deltas, pace components, residuals, and stint-level statistics "
            "(mean/median delta, delta trend, unexplained fraction). Bounded sample of "
            "evenly spaced clean laps (max 6). Deterministic; INSUFFICIENT_EVIDENCE when "
            "the stint lacks common clean laps or telemetry.",
            {
                "season": SEASON_PARAM, "round": ROUND_PARAM,
                "session_type": SESSION_TYPE_PARAM,
                "driver_a": {"type": "string"},
                "driver_b": {"type": "string"},
                "stint_number": {"type": "integer", "minimum": 1},
                "max_laps": {"type": "integer", "minimum": 2, "maximum": 12,
                             "description": "Bounded sample of stint laps (default 6)"},
            },
            ["season", "round", "driver_a", "driver_b", "stint_number"],
            {"type": "object", "additionalProperties": True, "required": ["status"]},
            [
                "Aggregates deterministic per-lap attributions; no new model beyond the "
                "lap-level straight-line region loss.",
                "Bounded output: max 12 per-lap entries.",
            ],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        from racewise.data.historical.loss_attribution import attribute_stint_loss

        return attribute_stint_loss(
            self._queries,
            season=int(kwargs["season"]),
            round_num=int(kwargs["round"]),
            driver_a=_normalize_driver_key(
                self._queries, str(kwargs["driver_a"]),
                int(kwargs["season"]), int(kwargs["round"]),
                str(kwargs.get("session_type", "RACE")).upper(),
            ),
            driver_b=_normalize_driver_key(
                self._queries, str(kwargs["driver_b"]),
                int(kwargs["season"]), int(kwargs["round"]),
                str(kwargs.get("session_type", "RACE")).upper(),
            ),
            stint_number=int(kwargs["stint_number"]),
            session_type=str(kwargs.get("session_type", "RACE")).upper(),
            max_laps=int(kwargs.get("max_laps", 6)),
        )


class FuseLapEvidenceTool(Tool):
    """Phase 6F evidence fusion: combine independent canonical evidence
    sources (sectors, telemetry metrics, stints, weather, race control,
    pit stops) into formal hypothesis verdicts for a measured lap delta."""

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self.spec = _spec(
            "fuse_historical_lap_evidence",
            "Fuse independent canonical evidence sources for a measured lap-time delta "
            "(driver B vs driver A): measured observation, authoritative sector "
            "decomposition, per-source evidence items with SUPPORTS/CONTRADICTS/"
            "DOES_NOT_TEST relationships, formally evaluated hypotheses (SUPPORTED/"
            "PARTIALLY_SUPPORTED/NOT_SUPPORTED/CONTRADICTED/NOT_TESTABLE/"
            "INSUFFICIENT_EVIDENCE), the preserved unexplained residual, and an "
            "evidence-bounded conclusion. No single confidence score; consistency is "
            "never reported as causation. Deterministic; UNAVAILABLE when laps or "
            "telemetry are missing.",
            {
                "season": SEASON_PARAM, "round": ROUND_PARAM,
                "session_type": SESSION_TYPE_PARAM,
                "driver_a": {"type": "string", "description": "Reference driver key, e.g. max-verstappen"},
                "driver_b": {"type": "string", "description": "Comparison driver key, e.g. sergio-perez"},
                "lap_number": {"type": "integer", "minimum": 1},
            },
            ["season", "round", "driver_a", "driver_b", "lap_number"],
            {"type": "object", "additionalProperties": True, "required": ["status"]},
            [
                "Consistency is not causation: SUPPORTED hypotheses describe evidence "
                "agreement, not proven cause.",
                "The unexplained residual is reported explicitly and never assigned to "
                "a hypothesis.",
                "Bounded: one lap, fixed source set, no raw telemetry dumps.",
            ],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        from racewise.data.historical.evidence_fusion import fuse_lap_evidence

        return fuse_lap_evidence(
            self._queries,
            season=int(kwargs["season"]),
            round_num=int(kwargs["round"]),
            driver_a=_normalize_driver_key(
                self._queries, str(kwargs["driver_a"]),
                int(kwargs["season"]), int(kwargs["round"]),
                str(kwargs.get("session_type", "RACE")).upper(),
            ),
            driver_b=_normalize_driver_key(
                self._queries, str(kwargs["driver_b"]),
                int(kwargs["season"]), int(kwargs["round"]),
                str(kwargs.get("session_type", "RACE")).upper(),
            ),
            lap_number=int(kwargs["lap_number"]),
            session_type=str(kwargs.get("session_type", "RACE")).upper(),
        )


def build_historical_registry(queries: CanonicalQueries) -> ToolRegistry:
    """Registry of canonical historical tools (composable with the FastF1 tools)."""
    registry = ToolRegistry()
    for tool in (
        GetHistoricalSessionTool(queries),
        GetTelemetrySummaryTool(queries),
        GetLapTelemetryTool(queries),
        CompareTelemetryLapTool(queries),
        GetHistoricalResultsTool(queries),
        GetHistoricalQualifyingTool(queries),
        GetHistoricalPitStopsTool(queries),
        GetHistoricalFastestLapsTool(queries),
        GetHistoricalStintsTool(queries),
        GetHistoricalWeatherTool(queries),
        GetHistoricalRaceControlTool(queries),
        SearchHistoricalCatalogTool(queries),
        AttributeLapLossTool(queries),
        AttributeStintLossTool(queries),
        FuseLapEvidenceTool(queries),
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
