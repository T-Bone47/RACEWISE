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


class FuseStintEvidenceTool(Tool):
    """Phase 6G stint-level evidence fusion: how the lap-delta explanation
    evolved across one stint - trajectory, trend, hypothesis evolution,
    residual trajectory, context transitions and change-point analysis."""

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self.spec = _spec(
            "fuse_historical_stint_evidence",
            "Fuse evidence across one stint (canonical stint identity) for a driver pair: "
            "deterministic common-lap selection with exclusion reasons, per-lap Phase 6F "
            "fusions preserved as a temporal sequence, OLS performance trend with a "
            "minimum-observation rule, telemetry metric trends, hypothesis evolution "
            "(CONSISTENTLY_SUPPORTED / MOSTLY_SUPPORTED / INTERMITTENTLY_SUPPORTED / "
            "CONTRADICTED_OVER_TIME / NOT_SUPPORTED / INSUFFICIENT_EVIDENCE), residual "
            "trajectory with cumulative conservation, context transitions, bounded "
            "change-point analysis, and an evidence-bounded conclusion. Consistency over "
            "time is not causation. UNAVAILABLE when stint identity is missing; "
            "INSUFFICIENT_EVIDENCE below 2 common clean laps.",
            {
                "season": SEASON_PARAM, "round": ROUND_PARAM,
                "session_type": SESSION_TYPE_PARAM,
                "driver_a": {"type": "string", "description": "Reference driver key, e.g. max-verstappen"},
                "driver_b": {"type": "string", "description": "Comparison driver key"},
                "stint_number": {"type": "integer", "minimum": 1},
                "max_laps": {"type": "integer", "minimum": 2, "maximum": 16,
                             "description": "Bounded evenly spaced sample across the stint (default 10)"},
            },
            ["season", "round", "driver_a", "driver_b", "stint_number"],
            {"type": "object", "additionalProperties": True, "required": ["status"]},
            [
                "Temporal summaries are descriptive facts about evidence status over laps, "
                "not confidence scores and not causal claims.",
                "The cumulative gap covers the selected comparable laps only; semantics are "
                "stated in the output and must not be overstated as race time lost.",
                "Bounded: max 16 laps, fixed source set, no raw telemetry dumps.",
            ],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        from racewise.data.historical.stint_evidence import fuse_stint_evidence

        # explicit bound enforcement: the generic payload validator does not
        # check numeric ranges, so reject unbounded max_laps here
        max_laps = int(kwargs.get("max_laps", 10))
        if not 2 <= max_laps <= 16:
            raise ToolError(
                "max_laps must be between 2 and 16",
                code="invalid_input",
                field="fuse_historical_stint_evidence.max_laps",
            )

        return fuse_stint_evidence(
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
            max_laps=int(kwargs.get("max_laps", 10)),
        )


class DecomposeRaceGapTool(Tool):
    """Phase 6H race-level gap decomposition: chronological timeline, official
    vs analytical gap, stint segments, gap events, pit/race-control windows,
    race-level hypothesis evolution and residual accounting."""

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self.spec = _spec(
            "decompose_historical_race_gap",
            "Decompose a race-level performance gap (driver B vs driver A) into a "
            "deterministic evidence map: official classified gap from canonical results "
            "(authoritative, never reconstructed from lap sums), cumulative comparable-lap "
            "gap (a different quantity, never forced to reconcile), chronological lap "
            "timeline with comparability classification and exclusion reasons, stint "
            "segments with descriptive gap patterns, bounded Phase 6G stint-evidence "
            "chaining, pit-window and race-control windows, gap events, race-level "
            "hypothesis evolution, and residual accounting with itemized unavailable "
            "intervals. Observed-gap language is not time-lost causation.",
            {
                "season": SEASON_PARAM, "round": ROUND_PARAM,
                "session_type": SESSION_TYPE_PARAM,
                "driver_a": {"type": "string", "description": "Reference driver key, e.g. max-verstappen"},
                "driver_b": {"type": "string", "description": "Comparison driver key"},
                "max_segments": {"type": "integer", "minimum": 2, "maximum": 24,
                                 "description": "Bounded stint-evidence chaining (default 12)"},
            },
            ["season", "round", "driver_a", "driver_b"],
            {"type": "object", "additionalProperties": True, "required": ["status"]},
            [
                "Official final gap and analytical comparable gap are different quantities "
                "and are never forced to reconcile.",
                "Non-comparable and unavailable intervals are preserved with reasons.",
                "Bounded: max_segments caps stint-evidence chaining; no raw telemetry dumps.",
            ],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        from racewise.data.historical.race_gap import decompose_race_gap

        # explicit numeric bound enforcement: the generic payload validator does
        # not check numeric ranges, so reject unbounded max_segments here
        max_segments = int(kwargs.get("max_segments", 12))
        if not 2 <= max_segments <= 24:
            raise ToolError(
                "max_segments must be between 2 and 24",
                code="invalid_input",
                field="decompose_historical_race_gap.max_segments",
            )

        return decompose_race_gap(
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
            session_type=str(kwargs.get("session_type", "RACE")).upper(),
            max_segments=max_segments,
        )


class AnalyzePerformanceEnvelopeTool(Tool):
    """Phase 6J measured performance envelope & bounded scenario sensitivity:
    the driver's own measured speed band over clean comparable laps, swept
    through the Phase 6I validated lap-time model."""

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self.spec = _spec(
            "analyze_historical_performance_envelope",
            "Build the MEASURED performance envelope for a driver (per grid point "
            "min/max/median of their own clean comparable laps - not an ideal lap "
            "or theoretical maximum) and run a bounded, typed scenario sweep "
            "(OBSERVED / DEFICIT_REDUCTION / REFERENCE_BLEND / ENVELOPE_LOWER_BOUND / "
            "ENVELOPE_UPPER_BOUND) through the Phase 6I validated fixed-distance "
            "lap-time model. Reports the sweep deltas, a descriptive finite-difference "
            "response classification (MONOTONIC / NON_MONOTONIC / FLAT / "
            "INSUFFICIENT_DATA), regional model sensitivity, and - for stint scope - "
            "a per-lap sensitivity trend to interpret alongside canonical degradation "
            "evidence. Scenario results cover only the sampled measured laps; no "
            "race-wide extrapolation. Every delta is model sensitivity, not history, "
            "not prediction, not causality.",
            {
                "season": SEASON_PARAM, "round": ROUND_PARAM,
                "session_type": SESSION_TYPE_PARAM,
                "driver": {"type": "string", "description": "Target driver key, e.g. sergio-perez"},
                "reference_driver": {"type": "string", "description": "Reference driver key (required for DEFICIT_REDUCTION, REFERENCE_BLEND and stint scope)"},
                "scenario_type": {"type": "string", "enum": list(
                    ("OBSERVED", "DEFICIT_REDUCTION", "REFERENCE_BLEND",
                     "ENVELOPE_LOWER_BOUND", "ENVELOPE_UPPER_BOUND"))},
                "parameter": {"type": "number", "description": "Anchor parameter within bounds (sweep covers the full range)"},
                "lap_number": {"type": "integer", "minimum": 1, "description": "Anchor lap; defaults to the first clean telemetry-covered lap"},
                "stint_number": {"type": "integer", "minimum": 1, "description": "Stint scope via Phase 6G common-lap selection (requires reference_driver)"},
                "max_scenarios": {"type": "integer", "minimum": 2, "maximum": 11,
                                  "description": "Bounded sweep size (default 5, cap 11)"},
                "max_laps": {"type": "integer", "minimum": 2, "maximum": 12,
                             "description": "Bounded envelope sample (default 6, cap 12)"},
                "segment_s": {"type": "number", "description": "Lap-time model segment width in seconds (2-30, default 6)"},
            },
            ["season", "round", "driver", "scenario_type"],
            {"type": "object", "additionalProperties": True, "required": ["status"]},
            [
                "The envelope is measured driver variability - never an ideal lap, "
                "theoretical maximum, or prediction.",
                "Scenario deltas are model sensitivities under specified interventions; "
                "they do not establish historical causality.",
                "Bounded: max 11 scenarios, max 12 laps, typed scenarios only; "
                "race-wide extrapolation is not offered.",
            ],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        from racewise.data.historical.performance_envelope import analyze_performance_envelope

        # explicit numeric bound enforcement: the generic payload validator
        # does not check numeric ranges, so re-validate here
        max_scenarios = int(kwargs.get("max_scenarios", 5))
        if not 2 <= max_scenarios <= 11:
            raise ToolError(
                "max_scenarios must be between 2 and 11",
                code="invalid_input",
                field="analyze_historical_performance_envelope.max_scenarios",
            )
        max_laps = int(kwargs.get("max_laps", 6))
        if not 2 <= max_laps <= 12:
            raise ToolError(
                "max_laps must be between 2 and 12",
                code="invalid_input",
                field="analyze_historical_performance_envelope.max_laps",
            )
        segment_s = float(kwargs.get("segment_s", 6.0))
        if not 2.0 <= segment_s <= 30.0:
            raise ToolError(
                "segment_s must be between 2 and 30",
                code="invalid_input",
                field="analyze_historical_performance_envelope.segment_s",
            )
        parameter = kwargs.get("parameter")
        if parameter is not None:
            parameter = float(parameter)
            if parameter != parameter or abs(parameter) > 1.0:
                raise ToolError(
                    "parameter must be finite and within [-1.0, 1.0]",
                    code="invalid_input",
                    field="analyze_historical_performance_envelope.parameter",
                )

        return analyze_performance_envelope(
            self._queries,
            season=int(kwargs["season"]),
            round_num=int(kwargs["round"]),
            driver=_normalize_driver_key(
                self._queries, str(kwargs["driver"]),
                int(kwargs["season"]), int(kwargs["round"]),
                str(kwargs.get("session_type", "RACE")).upper(),
            ),
            scenario_type=str(kwargs["scenario_type"]),
            parameter=parameter,
            reference_driver=(
                _normalize_driver_key(
                    self._queries, str(kwargs["reference_driver"]),
                    int(kwargs["season"]), int(kwargs["round"]),
                    str(kwargs.get("session_type", "RACE")).upper(),
                )
                if kwargs.get("reference_driver") else None
            ),
            lap_number=int(kwargs["lap_number"]) if kwargs.get("lap_number") else None,
            session_type=str(kwargs.get("session_type", "RACE")).upper(),
            max_scenarios=max_scenarios,
            max_laps=max_laps,
            segment_s=segment_s,
            stint_number=int(kwargs["stint_number"]) if kwargs.get("stint_number") else None,
        )


class SimulateTelemetryCounterfactualTool(Tool):
    """Phase 6I validated telemetry counterfactual: apply a bounded speed-profile
    intervention and run the deterministic fixed-distance lap-time model, with
    six validation gates including exact baseline reproduction."""

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self.spec = _spec(
            "simulate_historical_telemetry_counterfactual",
            "Simulate a validated telemetry counterfactual for one lap: extract the "
            "deterministic speed profile (Phase 6E alignment), apply a bounded "
            "intervention (REMOVE_DEFICIT / BLEND_WITH_REFERENCE vs a reference driver, "
            "or reference-free SCALE_SIGNAL), and integrate the fixed-distance segment "
            "lap-time model. Validation gates include exact baseline reproduction "
            "(model baseline == measured grid duration) and identity-parameter delta == 0. "
            "Only speed has a lap-time model in this codebase: interventions on throttle, "
            "brake, gear, rpm or drs return UNSUPPORTED - no physics is invented. The "
            "result measures MODEL SENSITIVITY to the intervention; it is not a historical "
            "fact, not a prediction, and not a causal proof.",
            {
                "season": SEASON_PARAM, "round": ROUND_PARAM,
                "session_type": SESSION_TYPE_PARAM,
                "driver": {"type": "string", "description": "Target driver key, e.g. sergio-perez"},
                "reference_driver": {"type": "string", "description": "Reference driver key (required for REMOVE_DEFICIT and BLEND_WITH_REFERENCE)"},
                "lap_number": {"type": "integer", "minimum": 1},
                "signal": {"type": "string", "enum": ["speed", "throttle", "brake", "gear", "rpm", "drs"]},
                "intervention_type": {"type": "string", "enum": ["REMOVE_DEFICIT", "BLEND_WITH_REFERENCE", "SCALE_SIGNAL"]},
                "fraction": {"type": "number", "description": "Intervention parameter; bounds depend on type (REMOVE_DEFICIT/BLEND [0,1], SCALE [-0.10, 0.10])"},
                "segment_s": {"type": "number", "description": "Segment width for the lap-time model in seconds (2-30, default 6)"},
            },
            ["season", "round", "driver", "lap_number", "signal", "intervention_type", "fraction"],
            {"type": "object", "additionalProperties": True, "required": ["status"]},
            [
                "The counterfactual result is model sensitivity under the specified "
                "deterministic intervention - never causality, history, or a prediction.",
                "Non-speed signals return UNSUPPORTED; out-of-bounds fractions raise errors.",
                "Bounded: single lap, fixed signal set, no raw telemetry dumps.",
            ],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        from racewise.data.historical.counterfactual import simulate_telemetry_counterfactual

        # explicit numeric bound enforcement: the generic payload validator
        # does not check numeric ranges, so re-validate here
        fraction = float(kwargs["fraction"])
        if fraction != fraction or fraction in (float("inf"), float("-inf")) or abs(fraction) > 1.0:
            raise ToolError(
                "fraction must be finite and within [-1.0, 1.0]",
                code="invalid_input",
                field="simulate_historical_telemetry_counterfactual.fraction",
            )
        segment_s = float(kwargs.get("segment_s", 6.0))
        if not 2.0 <= segment_s <= 30.0:
            raise ToolError(
                "segment_s must be between 2 and 30",
                code="invalid_input",
                field="simulate_historical_telemetry_counterfactual.segment_s",
            )

        return simulate_telemetry_counterfactual(
            self._queries,
            season=int(kwargs["season"]),
            round_num=int(kwargs["round"]),
            driver=_normalize_driver_key(
                self._queries, str(kwargs["driver"]),
                int(kwargs["season"]), int(kwargs["round"]),
                str(kwargs.get("session_type", "RACE")).upper(),
            ),
            lap_number=int(kwargs["lap_number"]),
            signal=str(kwargs["signal"]),
            intervention_type=str(kwargs["intervention_type"]),
            fraction=fraction,
            reference_driver=(
                _normalize_driver_key(
                    self._queries, str(kwargs["reference_driver"]),
                    int(kwargs["season"]), int(kwargs["round"]),
                    str(kwargs.get("session_type", "RACE")).upper(),
                )
                if kwargs.get("reference_driver") else None
            ),
            session_type=str(kwargs.get("session_type", "RACE")).upper(),
            segment_s=segment_s,
        )


class AnalyzePerformanceRegimesTool(Tool):
    """Phase 6K performance regime & change-point intelligence: deterministic
    temporal segmentation of a race's comparable-lap delta series."""

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self.spec = _spec(
            "analyze_historical_performance_regimes",
            "Detect performance regimes in a race for a driver pair: deterministic "
            "top-down OLS slope segmentation of the comparable-lap delta series "
            "(documented thresholds, MIN_REGIME_LAPS=3, SSE-improvement gate, "
            "deterministic merging) with every rejected candidate logged. Each "
            "regime carries gap pattern, speed-profile distance where paired "
            "telemetry exists, Phase 6F hypothesis evolution, residual accounting "
            "(reported, never assigned) and Phase 6J model sensitivity. Change "
            "points align temporally with context transitions (stint, pit, "
            "race-control, weather, compound, telemetry) as ASSOCIATIONS - never "
            "causality. Regimes are analytical, not canonical stints; telemetry "
            "gaps are preserved as explicit unavailable intervals.",
            {
                "season": SEASON_PARAM, "round": ROUND_PARAM,
                "session_type": SESSION_TYPE_PARAM,
                "driver_a": {"type": "string", "description": "Driver A key, e.g. max-verstappen"},
                "driver_b": {"type": "string", "description": "Driver B key (distinct from A)"},
                "max_regimes": {"type": "integer", "minimum": 2, "maximum": 12,
                                "description": "Bounded regime count (default 8, cap 12)"},
                "min_regime_laps": {"type": "integer", "description": "Fixed at 3 (documented deterministic threshold)"},
                "start_lap": {"type": "integer", "minimum": 1, "description": "Analysis window start"},
                "end_lap": {"type": "integer", "minimum": 1, "description": "Analysis window end (>= start_lap)"},
            },
            ["season", "round", "driver_a", "driver_b"],
            {"type": "object", "additionalProperties": True, "required": ["status"]},
            [
                "Regime detection identifies measured temporal structure; it does "
                "not establish causality.",
                "A transition temporally aligned with a context change is an "
                "association, not a causal claim.",
                "Bounded: max 12 regimes, fixed MIN_REGIME_LAPS=3, no confidence "
                "scores - states are DETECTED / NOT_DETECTED / INSUFFICIENT_EVIDENCE.",
            ],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        from racewise.data.historical.performance_regimes import analyze_performance_regimes

        # explicit numeric bound enforcement: the generic payload validator
        # does not check numeric ranges, so re-validate here
        max_regimes = int(kwargs.get("max_regimes", 8))
        if not 2 <= max_regimes <= 12:
            raise ToolError(
                "max_regimes must be between 2 and 12",
                code="invalid_input",
                field="analyze_historical_performance_regimes.max_regimes",
            )
        min_regime_laps = int(kwargs.get("min_regime_laps", 3))
        if min_regime_laps != 3:
            raise ToolError(
                "min_regime_laps is fixed at 3 (documented deterministic threshold)",
                code="invalid_input",
                field="analyze_historical_performance_regimes.min_regime_laps",
            )
        start_lap = int(kwargs["start_lap"]) if kwargs.get("start_lap") is not None else None
        end_lap = int(kwargs["end_lap"]) if kwargs.get("end_lap") is not None else None
        if start_lap is not None and start_lap < 1:
            raise ToolError(
                "start_lap must be >= 1",
                code="invalid_input",
                field="analyze_historical_performance_regimes.start_lap",
            )
        if end_lap is not None and end_lap < 1:
            raise ToolError(
                "end_lap must be >= 1",
                code="invalid_input",
                field="analyze_historical_performance_regimes.end_lap",
            )
        if start_lap is not None and end_lap is not None and start_lap > end_lap:
            raise ToolError(
                "start_lap must be <= end_lap",
                code="invalid_input",
                field="analyze_historical_performance_regimes.start_lap",
            )

        season = int(kwargs["season"])
        round_num = int(kwargs["round"])
        session_type = str(kwargs.get("session_type", "RACE")).upper()
        driver_a = _normalize_driver_key(
            self._queries, str(kwargs["driver_a"]), season, round_num, session_type)
        driver_b = _normalize_driver_key(
            self._queries, str(kwargs["driver_b"]), season, round_num, session_type)
        if driver_a == driver_b:
            raise ToolError(
                "driver_a and driver_b must be distinct",
                code="invalid_input",
                field="analyze_historical_performance_regimes.driver_b",
            )
        return analyze_performance_regimes(
            self._queries,
            season=season,
            round_num=round_num,
            driver_a=driver_a,
            driver_b=driver_b,
            max_regimes=max_regimes,
            min_regime_laps=min_regime_laps,
            start_lap=start_lap,
            end_lap=end_lap,
        )


class AnalyzeCrossRacePerformancePatternsTool(Tool):
    """Phase 6L cross-race performance pattern intelligence: deterministic
    recurrence detection over Phase 6K regime signatures."""

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self.spec = _spec(
            "analyze_cross_race_performance_patterns",
            "Detect RECURRING performance-regime structures across races for a "
            "driver pair: Phase 6K regimes are summarized into deterministic "
            "signatures, grouped by canonical structural keys, refined with "
            "explicit component-distance matching (slope/duration/residual/" 
            "envelope/sensitivity, documented thresholds, no clustering, no ML) "
            "and reported when observed in at least MIN_RECURRING_RACES=2 "
            "independent races. Every pattern carries occurrence facets, context "
            "associations, per-hypothesis consistency (6F vocabulary), a "
            "falsification summary (contradictions preserved), residual pattern "
            "states (never assigned), Phase 6J/6I model sensitivity comparison "
            "and full provenance. A recurring pattern is NOT a cause; no "
            "confidence scores; no rankings.",
            {
                "driver_a": {"type": "string", "description": "Driver A key, e.g. max-verstappen"},
                "driver_b": {"type": "string", "description": "Driver B key (distinct from A)"},
                "seasons": {"type": "array", "items": {"type": "integer"},
                            "description": "Bounded season list (default: all telemetry seasons)"},
                "rounds": {"type": "array", "items": {"type": "integer"},
                           "description": "Optional round filter within the seasons"},
                "circuit": {"type": "string",
                            "description": "Optional circuit-name filter"},
                "max_races": {"type": "integer", "minimum": 1, "maximum": 20,
                              "description": "Bounded race corpus (default 8, cap 20)"},
                "max_patterns": {"type": "integer", "minimum": 1, "maximum": 50,
                                 "description": "Bounded pattern count (default 20, cap 50)"},
            },
            ["driver_a", "driver_b"],
            {"type": "object", "additionalProperties": True, "required": ["status"]},
            [
                "A recurring pattern is an observation of repetition across "
                "independent race instances; it is not causation and not a "
                "significance claim.",
                "Structure states are deterministic threshold classifications, "
                "not confidence scores; races and drivers are never ranked.",
                "Bounded: max_races <= 20, max_patterns <= 50; unknown parameters "
                "are rejected; missing telemetry stays missing.",
            ],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        from racewise.data.historical.performance_patterns import (
            MAX_PATTERNS, MAX_RACES, analyze_cross_race_performance_patterns,
        )

        # explicit numeric bound enforcement: the generic payload validator
        # does not check numeric ranges, so re-validate here
        max_races = int(kwargs.get("max_races", 8))
        if not 1 <= max_races <= MAX_RACES:
            raise ToolError(
                f"max_races must be between 1 and {MAX_RACES}",
                code="invalid_input",
                field="analyze_cross_race_performance_patterns.max_races",
            )
        max_patterns = int(kwargs.get("max_patterns", 20))
        if not 1 <= max_patterns <= MAX_PATTERNS:
            raise ToolError(
                f"max_patterns must be between 1 and {MAX_PATTERNS}",
                code="invalid_input",
                field="analyze_cross_race_performance_patterns.max_patterns",
            )
        seasons = kwargs.get("seasons")
        if seasons is not None:
            if not isinstance(seasons, list) or not seasons or \
                    not all(isinstance(s, int) for s in seasons):
                raise ToolError(
                    "seasons must be a non-empty list of integers",
                    code="invalid_input",
                    field="analyze_cross_race_performance_patterns.seasons",
                )
        rounds = kwargs.get("rounds")
        if rounds is not None:
            if not isinstance(rounds, list) or not rounds or \
                    not all(isinstance(r, int) for r in rounds):
                raise ToolError(
                    "rounds must be a non-empty list of integers",
                    code="invalid_input",
                    field="analyze_cross_race_performance_patterns.rounds",
                )
        circuit = kwargs.get("circuit")
        if circuit is not None and (not isinstance(circuit, str)
                                    or not circuit.strip()):
            raise ToolError(
                "circuit must be a non-empty string when provided",
                code="invalid_input",
                field="analyze_cross_race_performance_patterns.circuit",
            )

        driver_a = _normalize_driver_key(
            self._queries, str(kwargs["driver_a"]),
            seasons[0] if seasons else None)
        driver_b = _normalize_driver_key(
            self._queries, str(kwargs["driver_b"]),
            seasons[0] if seasons else None)
        if driver_a == driver_b:
            raise ToolError(
                "driver_a and driver_b must be distinct",
                code="invalid_input",
                field="analyze_cross_race_performance_patterns.driver_b",
            )
        return analyze_cross_race_performance_patterns(
            self._queries,
            driver_a=driver_a,
            driver_b=driver_b,
            seasons=seasons,
            rounds=rounds,
            circuit=circuit,
            max_races=max_races,
            max_patterns=max_patterns,
        )


class AnalyzeCrossRacePatternEvidenceTool(Tool):
    """Phase 6M cross-race hypothesis & evidence intelligence: deterministic
    evidence aggregation over one recurring Phase 6L pattern."""

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self.spec = _spec(
            "analyze_cross_race_pattern_evidence",
            "Investigate the evidence behind one RECURRING cross-race "
            "performance pattern (Phase 6L): for each of the six Phase 6F "
            "hypotheses the tool aggregates the underlying 6G regime-hypothesis "
            "observations across independent race occurrences into a "
            "deterministic evidence matrix and aggregate states "
            "(CONSISTENTLY_SUPPORTED / MOSTLY_SUPPORTED / VARIABLE / "
            "CONTRADICTORY / CONSISTENTLY_NOT_SUPPORTED / "
            "INSUFFICIENT_EVIDENCE). Contradictions are preserved verbatim, "
            "never averaged away; residuals are reported, never assigned; "
            "model sensitivity stays a model property; missing evidence stays "
            "missing. A consistent aggregate is NOT causation and NO "
            "falsification found is NOT confirmation. No confidence scores, "
            "no rankings, no winner selection.",
            {
                "driver_a": {"type": "string", "description": "Driver A key, e.g. max-verstappen"},
                "driver_b": {"type": "string", "description": "Driver B key (distinct from A)"},
                "pattern_id": {"type": "string",
                               "description": "Recurring pattern_id from analyze_cross_race_performance_patterns"},
                "seasons": {"type": "array", "items": {"type": "integer"},
                            "description": "Optional bounded season filter (must contain the pattern)"},
                "rounds": {"type": "array", "items": {"type": "integer"},
                           "description": "Optional round filter within the seasons"},
                "circuit": {"type": "string",
                            "description": "Optional circuit-name filter"},
                "max_occurrences": {"type": "integer", "minimum": 1, "maximum": 8,
                                    "description": "Bounded occurrence subset (default 8, cap 8)"},
                "max_races": {"type": "integer", "minimum": 1, "maximum": 20,
                              "description": "6L corpus width used to form patterns (default 8, cap 20). Use the same value the pattern was browsed with."},
            },
            ["driver_a", "driver_b", "pattern_id"],
            {"type": "object", "additionalProperties": True, "required": ["status"]},
            [
                "Aggregate evidence states are deterministic classifications of "
                "measured 6F/6G observations, not confidence scores; SUPPORT != "
                "PROOF and NO_FALSIFICATION_FOUND != CONFIRMED.",
                "Contradictions between occurrences are preserved and reported "
                "per hypothesis; hypotheses are never ranked or collapsed.",
                "Bounded: max_occurrences <= 8; unknown parameters are rejected; "
                "missing telemetry/evidence stays missing.",
            ],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        from racewise.data.historical.performance_evidence import (
            MAX_OCCURRENCES, MIN_OCCURRENCES,
            analyze_cross_race_pattern_evidence,
        )
        from racewise.data.historical.performance_patterns import MAX_RACES

        # explicit boundary re-validation (generic payload validation does not
        # check numeric ranges or list shapes)
        max_occurrences = int(kwargs.get("max_occurrences", MAX_OCCURRENCES))
        if not MIN_OCCURRENCES <= max_occurrences <= MAX_OCCURRENCES:
            raise ToolError(
                f"max_occurrences must be between {MIN_OCCURRENCES} and "
                f"{MAX_OCCURRENCES}",
                code="invalid_input",
                field="analyze_cross_race_pattern_evidence.max_occurrences",
            )
        max_races = int(kwargs.get("max_races", 8))
        if not 1 <= max_races <= MAX_RACES:
            raise ToolError(
                f"max_races must be between 1 and {MAX_RACES}",
                code="invalid_input",
                field="analyze_cross_race_pattern_evidence.max_races",
            )
        pattern_id = kwargs.get("pattern_id")
        if not isinstance(pattern_id, str) or not pattern_id.strip():
            raise ToolError(
                "pattern_id must be a non-empty string",
                code="invalid_input",
                field="analyze_cross_race_pattern_evidence.pattern_id",
            )
        seasons = kwargs.get("seasons")
        if seasons is not None:
            if not isinstance(seasons, list) or not seasons or \
                    not all(isinstance(s, int) for s in seasons):
                raise ToolError(
                    "seasons must be a non-empty list of integers",
                    code="invalid_input",
                    field="analyze_cross_race_pattern_evidence.seasons",
                )
        rounds = kwargs.get("rounds")
        if rounds is not None:
            if not isinstance(rounds, list) or not rounds or \
                    not all(isinstance(r, int) for r in rounds):
                raise ToolError(
                    "rounds must be a non-empty list of integers",
                    code="invalid_input",
                    field="analyze_cross_race_pattern_evidence.rounds",
                )
        circuit = kwargs.get("circuit")
        if circuit is not None and (not isinstance(circuit, str)
                                    or not circuit.strip()):
            raise ToolError(
                "circuit must be a non-empty string when provided",
                code="invalid_input",
                field="analyze_cross_race_pattern_evidence.circuit",
            )

        driver_a = _normalize_driver_key(
            self._queries, str(kwargs["driver_a"]),
            seasons[0] if seasons else None)
        driver_b = _normalize_driver_key(
            self._queries, str(kwargs["driver_b"]),
            seasons[0] if seasons else None)
        if driver_a == driver_b:
            raise ToolError(
                "driver_a and driver_b must be distinct",
                code="invalid_input",
                field="analyze_cross_race_pattern_evidence.driver_b",
            )
        return analyze_cross_race_pattern_evidence(
            self._queries,
            driver_a=driver_a,
            driver_b=driver_b,
            pattern_id=pattern_id,
            seasons=seasons,
            rounds=rounds,
            circuit=circuit,
            max_occurrences=max_occurrences,
            max_races=max_races,
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
        FuseStintEvidenceTool(queries),
        DecomposeRaceGapTool(queries),
        SimulateTelemetryCounterfactualTool(queries),
        AnalyzePerformanceEnvelopeTool(queries),
        AnalyzePerformanceRegimesTool(queries),
        AnalyzeCrossRacePerformancePatternsTool(queries),
        AnalyzeCrossRacePatternEvidenceTool(queries),
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
