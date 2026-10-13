"""Concrete deterministic tools exposed to the agent.

Each tool wraps pure analytics functions behind the Tool contract with
explicit input/output schemas and versions. The agent can only call these;
it never receives raw dataframe access.
"""
from __future__ import annotations

import statistics
from typing import Any, Optional

from racewise.data.fastf1_adapter import FastF1Adapter
from racewise.domain.schemas import Lap
from racewise.tools.analytics import (
    ANALYTICS_VERSION,
    compare_sectors,
    delta_time_between_drivers,
    detect_pace_anomaly,
    filter_clean_laps,
    linear_degradation,
    pace_summary,
    stint_laps,
    traffic_exposure,
)
from racewise.tools.contract import Tool, ToolError, ToolRegistry, ToolSpec
from racewise.tools.race_state import (
    RACE_STATE_VERSION,
    cars_ahead_at_lap,
    compound_of_lap,
    laps_for_driver,
    laps_in_window,
    mean_pace,
    position_at_lap,
    stint_boundary_laps,
    time_gap_at_lap,
)
from racewise.simulator.strategy import (
    SIMULATOR_VERSION,
    compare_strategy_scenarios,
    simulate_compound_change,
    simulate_pit_timing,
)

PIT_LOSS_VERSION = "1.0.0"


def _lap_dict(lap: Lap) -> dict[str, Any]:
    return {
        "driver": lap.driver,
        "lap_number": lap.lap_number,
        "lap_time_s": lap.lap_time_s,
        "compound": lap.compound,
        "tyre_life": lap.tyre_life,
        "stint": lap.stint,
        "position": lap.position,
        "is_pit_in_lap": lap.is_pit_in_lap,
        "is_pit_out_lap": lap.is_pit_out_lap,
        "track_status": lap.track_status,
    }


class SessionContext:
    """Holds one loaded session's normalized data for tool execution."""

    def __init__(self, adapter: FastF1Adapter, year: int, event: str, session_type: str = "R") -> None:
        self.adapter = adapter
        self.year = year
        self.event = event
        self.session_type = session_type
        self._session: Any = None
        self._laps: Optional[list[Lap]] = None
        self._summary: Optional[SessionSummary] = None

    def load(self) -> None:
        if self._session is None:
            self._session = self.adapter.load_session(self.year, self.event, self.session_type)
            self._laps = self.adapter.laps(self._session)
            self._summary = self.adapter.session_summary(self._session)

    @property
    def laps(self) -> list[Lap]:
        self.load()
        assert self._laps is not None
        return self._laps

    @property
    def summary(self) -> SessionSummary:
        self.load()
        assert self._summary is not None
        return self._summary

    def driver_laps(self, driver: str) -> list[Lap]:
        if driver not in self.summary.drivers:
            raise ToolError(f"Driver '{driver}' not found in session", missing=True, code="missing_data", field="driver")
        return laps_for_driver(self.laps, driver)


class GetSessionTool(Tool):
    """Session metadata: event, circuit, drivers, lap totals."""

    def __init__(self, context: SessionContext) -> None:
        self._context = context
        self.spec = ToolSpecWrapper(
            name="get_session",
            description="Return session metadata: event name, circuit, session type, driver list, total lap count.",
            input_schema={"type": "object", "properties": {}, "required": []},
            output_schema={
                "type": "object",
                "properties": {
                    "event_name": {"type": "string"},
                    "session_type": {"type": "string"},
                    "date": OUT_TRACK_STATUS,
                    "circuit": OUT_COMPOUND,
                    "total_laps": OUT_POSITION,
                    "drivers": {"type": "array", "items": {"type": "string"}},
                    "n_drivers": {"type": "integer"},
                },
                "required": ["event_name", "session_type", "date", "circuit", "total_laps", "drivers", "n_drivers"],
            },
            version="1.0.0",
            limitations=["Historical data only; no live sessions."],
        ).spec

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        summary = self._context.summary
        return {
            "event_name": summary.event_name,
            "session_type": summary.session_type,
            "date": summary.date.isoformat() if summary.date else None,
            "circuit": summary.circuit,
            "total_laps": summary.total_laps,
            "drivers": summary.drivers,
            "n_drivers": len(summary.drivers),
        }


class ToolSpecWrapper:
    def __init__(self, name: str, description: str, input_schema: dict, output_schema: dict, version: str, limitations: Optional[list] = None) -> None:
        self.spec = ToolSpec(
            name=name,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            version=version,
            limitations=limitations or [],
        )


def _spec(name: str, description: str, properties: dict, required: list[str], version: str, output_schema: dict, limitations: Optional[list[str]] = None) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        input_schema={"type": "object", "properties": properties, "required": required},
        output_schema=output_schema,
        version=version,
        limitations=limitations or [],
    )


DRIVER_PARAM = {"type": "string", "description": "Three-letter driver code, e.g. VER"}
LAP_START_PARAM = {"type": "integer", "description": "First lap number of window"}
LAP_END_PARAM = {"type": "integer", "description": "Last lap number of window"}

OUT_DRIVER = {"type": "string"}
OUT_LAP_NUMBER = {"type": "integer"}
OUT_LAP_TIME_S = {"type": ["number", "null"]}
OUT_COMPOUND = {"type": ["string", "null"]}
OUT_TYRE_LIFE = {"type": ["integer", "null"]}
OUT_STINT = {"type": ["integer", "null"]}
OUT_POSITION = {"type": ["integer", "null"]}
OUT_BOOL = {"type": "boolean"}
OUT_TRACK_STATUS = {"type": ["string", "null"]}

LAP_RECORD_SCHEMA = {
    "type": "object",
    "properties": {
        "driver": OUT_DRIVER,
        "lap_number": OUT_LAP_NUMBER,
        "lap_time_s": OUT_LAP_TIME_S,
        "compound": OUT_COMPOUND,
        "tyre_life": OUT_TYRE_LIFE,
        "stint": OUT_STINT,
        "position": OUT_POSITION,
        "is_pit_in_lap": OUT_BOOL,
        "is_pit_out_lap": OUT_BOOL,
        "track_status": OUT_TRACK_STATUS,
    },
    "required": [
        "driver", "lap_number", "lap_time_s", "compound", "tyre_life",
        "stint", "position", "is_pit_in_lap", "is_pit_out_lap", "track_status",
    ],
}


class GetLapsTool(Tool):
    """Canonical laps for one driver."""

    def __init__(self, context: SessionContext) -> None:
        self._context = context
        self.spec = _spec(
            "get_laps",
            "Return normalized lap records for one driver: lap number, time, compound, tyre life, stint, position, pit flags.",
            {"driver": DRIVER_PARAM},
            ["driver"],
            "1.0.0",
            {
                "type": "object",
                "properties": {
                    "driver": OUT_DRIVER,
                    "n_laps": {"type": "integer"},
                    "laps": {"type": "array", "items": LAP_RECORD_SCHEMA},
                },
                "required": ["driver", "n_laps", "laps"],
            },
            ["Returns at most one season-race; includes pit in/out laps flagged."],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        laps = self._context.driver_laps(kwargs["driver"])
        return {"driver": kwargs["driver"], "n_laps": len(laps), "laps": [_lap_dict(lap) for lap in laps]}


class GetStintsTool(Tool):
    """Stint structure for one driver."""

    def __init__(self, context: SessionContext) -> None:
        self._context = context
        self.spec = _spec(
            "get_stints",
            "Return tyre stint windows for one driver: stint number, compound, start/end lap, lap count.",
            {"driver": DRIVER_PARAM},
            ["driver"],
            "1.0.0",
            {
                "type": "object",
                "properties": {
                    "driver": OUT_DRIVER,
                    "stints": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "stint": {"type": "integer"},
                                "compound": OUT_COMPOUND,
                                "lap_start": {"type": "integer"},
                                "lap_end": {"type": "integer"},
                                "lap_count": {"type": "integer"},
                            },
                            "required": ["stint", "compound", "lap_start", "lap_end", "lap_count"],
                        },
                    },
                },
                "required": ["driver", "stints"],
            },
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        driver = kwargs["driver"]
        driver_laps = self._context.driver_laps(driver)
        bounds = stint_boundary_laps(driver_laps, driver)
        stints = []
        for stint_number, (lap_start, lap_end) in sorted(bounds.items()):
            compounds = {lap.compound for lap in driver_laps if lap.stint == stint_number and lap.compound}
            stints.append(
                {
                    "stint": stint_number,
                    "compound": sorted(compounds)[0] if compounds else None,
                    "lap_start": lap_start,
                    "lap_end": lap_end,
                    "lap_count": lap_end - lap_start + 1,
                }
            )
        return {"driver": driver, "stints": stints}


class AnalyzeTyreDegradationTool(Tool):
    """Linear tyre degradation slope for a driver stint (clean laps)."""

    def __init__(self, context: SessionContext) -> None:
        self._context = context
        self.spec = _spec(
            "analyze_tyre_degradation",
            "Estimate lap-time degradation slope (s/lap) vs tyre life for one driver stint using clean laps only.",
            {"driver": DRIVER_PARAM, "stint": {"type": "integer", "description": "Stint number (1-based)"}},
            ["driver"],
            ANALYTICS_VERSION,
            {
                "type": "object",
                "properties": {
                    "driver": OUT_DRIVER,
                    "stint": OUT_STINT,
                    "per_stint": {
                        "type": ["object", "null"],
                        "additionalProperties": {
                            "type": ["object", "null"],
                            "properties": {
                                "slope_s_per_lap": {"type": "number"},
                                "intercept_s": {"type": "number"},
                                "r_squared": {"type": "number"},
                                "n_laps": {"type": "integer"},
                            },
                            "required": ["slope_s_per_lap", "intercept_s", "r_squared", "n_laps"],
                        },
                    },
                    "slope_s_per_lap": {"type": "number"},
                    "intercept_s": {"type": "number"},
                    "r_squared": {"type": "number"},
                    "n_laps": {"type": "integer"},
                },
                "required": ["driver"],
            },
            ["Linear model; unreliable for stints with < 3 clean laps or heavy traffic/fuel variation."],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        driver = kwargs["driver"]
        stint = kwargs.get("stint")
        driver_laps = self._context.driver_laps(driver)
        if stint is None:
            stints_present = sorted({lap.stint for lap in driver_laps if lap.stint is not None})
            results = {}
            for s in stints_present:
                clean = filter_clean_laps(stint_laps(driver_laps, driver, s))
                results[str(s)] = linear_degradation(clean)
            return {"driver": driver, "per_stint": results}
        clean = filter_clean_laps(stint_laps(driver_laps, driver, stint))
        deg = linear_degradation(clean)
        if deg is None:
            raise ToolError(f"Not enough clean laps in stint {stint} for {driver}", missing=True, code="missing_data", field="stint")
        return {"driver": driver, "stint": stint, **deg}


class AnalyzeTrafficTool(Tool):
    """Traffic exposure estimate for a driver lap window."""

    def __init__(self, context: SessionContext) -> None:
        self._context = context
        self.spec = _spec(
            "analyze_traffic",
            "Estimate traffic exposure for one driver over a lap window: which laps the car directly ahead was within a time threshold.",
            {
                "driver": DRIVER_PARAM,
                "lap_start": LAP_START_PARAM,
                "lap_end": LAP_END_PARAM,
                "gap_threshold_s": {"type": "number", "description": "Max gap to car ahead counted as traffic (default 1.0)"},
            },
            ["driver", "lap_start", "lap_end"],
            ANALYTICS_VERSION,
            {
                "type": "object",
                "properties": {
                    "window": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 2,
                        "maxItems": 2,
                    },
                    "laps_analyzed": {"type": "integer"},
                    "traffic_laps": {"type": "array", "items": {"type": "integer"}},
                    "traffic_fraction": {"type": "number"},
                    "exposure_detail": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "lap_number": {"type": "integer"},
                                "in_traffic": OUT_BOOL,
                                "gap_s": OUT_LAP_TIME_S,
                                "car_ahead": OUT_COMPOUND,
                            },
                            "required": ["lap_number", "in_traffic", "gap_s", "car_ahead"],
                        },
                    },
                },
                "required": ["window", "laps_analyzed", "traffic_laps", "traffic_fraction", "exposure_detail"],
            },
            ["Approximation from cumulative clean lap times; under safety car the estimate degrades."],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        result = traffic_exposure(
            self._context.laps,
            kwargs["driver"],
            int(kwargs["lap_start"]),
            int(kwargs["lap_end"]),
            float(kwargs.get("gap_threshold_s", 1.0)),
        )
        return result


class CompareSectorsTool(Tool):
    """Per-sector mean comparison between two drivers over a lap window."""

    def __init__(self, context: SessionContext) -> None:
        self._context = context
        self.spec = _spec(
            "compare_sectors",
            "Compare mean sector times between two drivers over matched lap windows; returns per-sector deltas.",
            {"driver_a": DRIVER_PARAM, "driver_b": DRIVER_PARAM, "lap_start": LAP_START_PARAM, "lap_end": LAP_END_PARAM},
            ["driver_a", "driver_b", "lap_start", "lap_end"],
            ANALYTICS_VERSION,
            {
                "type": "object",
                "properties": {
                    "a_means": {
                        "type": "object",
                        "properties": {
                            "sector_1_s": OUT_LAP_TIME_S,
                            "sector_2_s": OUT_LAP_TIME_S,
                            "sector_3_s": OUT_LAP_TIME_S,
                        },
                        "required": ["sector_1_s", "sector_2_s", "sector_3_s"],
                    },
                    "b_means": {
                        "type": "object",
                        "properties": {
                            "sector_1_s": OUT_LAP_TIME_S,
                            "sector_2_s": OUT_LAP_TIME_S,
                            "sector_3_s": OUT_LAP_TIME_S,
                        },
                        "required": ["sector_1_s", "sector_2_s", "sector_3_s"],
                    },
                    "delta_a_minus_b": {
                        "type": "object",
                        "properties": {
                            "sector_1_s": OUT_LAP_TIME_S,
                            "sector_2_s": OUT_LAP_TIME_S,
                            "sector_3_s": OUT_LAP_TIME_S,
                        },
                        "required": ["sector_1_s", "sector_2_s", "sector_3_s"],
                    },
                },
                "required": ["a_means", "b_means", "delta_a_minus_b"],
            },
            ["Sector times can be missing for some laps; means use available data."],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        laps = self._context.laps
        a = [
            lap
            for lap in laps_in_window(laps, kwargs["driver_a"], int(kwargs["lap_start"]), int(kwargs["lap_end"]))
            if lap.lap_time_s is not None and not lap.is_pit_in_lap and not lap.is_pit_out_lap
        ]
        b = [
            lap
            for lap in laps_in_window(laps, kwargs["driver_b"], int(kwargs["lap_start"]), int(kwargs["lap_end"]))
            if lap.lap_time_s is not None and not lap.is_pit_in_lap and not lap.is_pit_out_lap
        ]
        if not a or not b:
            raise ToolError("No comparable laps in window for one of the drivers", missing=True, code="missing_data", field="lap_start")
        result = compare_sectors(a, b)
        assert result is not None
        return result


class CompareDriverPaceTool(Tool):
    """Clean-lap pace comparison between two drivers, optionally per stint."""

    def __init__(self, context: SessionContext) -> None:
        self._context = context
        self.spec = _spec(
            "compare_driver_pace",
            "Compare mean and fastest clean-lap pace between two drivers; optionally restricted to a lap window.",
            {"driver_a": DRIVER_PARAM, "driver_b": DRIVER_PARAM, "lap_start": LAP_START_PARAM, "lap_end": LAP_END_PARAM},
            ["driver_a", "driver_b"],
            ANALYTICS_VERSION,
            {
                "type": "object",
                "properties": {
                    "driver_mean_s": {"type": "number"},
                    "reference_mean_s": {"type": "number"},
                    "delta_s": {"type": "number"},
                    "driver_fastest_s": {"type": "number"},
                    "reference_fastest_s": {"type": "number"},
                    "fastest_delta_s": {"type": "number"},
                    "driver_n_laps": {"type": "integer"},
                    "reference_n_laps": {"type": "integer"},
                },
                "required": [
                    "driver_mean_s", "reference_mean_s", "delta_s",
                    "driver_fastest_s", "reference_fastest_s", "fastest_delta_s",
                    "driver_n_laps", "reference_n_laps",
                ],
            },
            ["Uses IsAccurate filtering; results are approximations, not official classifications."],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        laps = self._context.laps
        start = int(kwargs["lap_start"]) if kwargs.get("lap_start") else None
        end = int(kwargs["lap_end"]) if kwargs.get("lap_end") else None

        def pick(driver: str) -> list[Lap]:
            driver_laps = laps_for_driver(laps, driver)
            if start is not None and end is not None:
                driver_laps = laps_in_window(driver_laps, driver, start, end)
            return filter_clean_laps(driver_laps)

        a = pick(kwargs["driver_a"])
        b = pick(kwargs["driver_b"])
        if not a or not b:
            raise ToolError("No clean laps for one of the drivers in the requested window", missing=True, code="missing_data", field="driver_a")
        result = delta_time_between_drivers(a, b)
        assert result is not None
        return result


class DetectPaceAnomalyTool(Tool):
    """Rolling-median anomaly detection over a driver's laps."""

    def __init__(self, context: SessionContext) -> None:
        self._context = context
        self.spec = _spec(
            "detect_pace_anomaly",
            "Flag laps slower than a rolling median by a robust threshold; useful for finding pace drops, traffic clusters or problems.",
            {"driver": DRIVER_PARAM, "lap_start": LAP_START_PARAM, "lap_end": LAP_END_PARAM},
            ["driver"],
            ANALYTICS_VERSION,
            {
                "type": "object",
                "properties": {
                    "driver": OUT_DRIVER,
                    "window": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 2,
                        "maxItems": 2,
                    },
                    "anomalies": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "lap_number": {"type": "integer"},
                                "lap_time_s": {"type": "number"},
                                "window_median_s": {"type": "number"},
                                "deviation_s": {"type": "number"},
                                "threshold_s": {"type": "number"},
                            },
                            "required": ["lap_number", "lap_time_s", "window_median_s", "deviation_s", "threshold_s"],
                        },
                    },
                },
                "required": ["driver", "window", "anomalies"],
            },
            ["Median/MAD heuristic; flags outliers but does not explain them."],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        driver = kwargs["driver"]
        driver_laps = self._context.driver_laps(driver)
        start = int(kwargs["lap_start"]) if kwargs.get("lap_start") else 1
        end = int(kwargs["lap_end"]) if kwargs.get("lap_end") else 10**6
        window = laps_in_window(driver_laps, driver, start, end)
        anomalies = detect_pace_anomaly(window)
        return {"driver": driver, "window": [start, end], "anomalies": anomalies}


class AnalyzePitLossTool(Tool):
    """Observed pit-cycle time loss for one driver's pit stops."""

    def __init__(self, context: SessionContext) -> None:
        self._context = context
        self.spec = _spec(
            "analyze_pit_loss",
            "Estimate total pit-cycle time loss (station + lane) per stop from in-lap vs out-lap times for one driver.",
            {"driver": DRIVER_PARAM},
            ["driver"],
            PIT_LOSS_VERSION,
            {
                "type": "object",
                "properties": {
                    "driver": OUT_DRIVER,
                    "median_clean_lap_s": {"type": "number"},
                    "stops": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "pit_in_lap": {"type": "integer"},
                                "in_lap_loss_s": OUT_LAP_TIME_S,
                                "out_lap_loss_s": OUT_LAP_TIME_S,
                                "total_loss_s": OUT_LAP_TIME_S,
                            },
                            "required": ["pit_in_lap", "in_lap_loss_s", "out_lap_loss_s", "total_loss_s"],
                        },
                    },
                    "mean_total_loss_s": OUT_LAP_TIME_S,
                },
                "required": ["driver", "median_clean_lap_s", "stops", "mean_total_loss_s"],
            },
            ["Approximation: compares pit in-lap and out-lap vs driver's rolling median lap time."],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        driver = kwargs["driver"]
        driver_laps = self._context.driver_laps(driver)
        timed = [lap for lap in driver_laps if lap.lap_time_s is not None and not lap.is_pit_in_lap and not lap.is_pit_out_lap]
        if len(timed) < 5:
            raise ToolError("Not enough timed laps to estimate pit loss", missing=True, code="missing_data", field="driver")
        baseline = statistics.median([lap.lap_time_s for lap in timed])
        stops = []
        for i, lap in enumerate(driver_laps):
            if not lap.is_pit_in_lap or lap.lap_time_s is None:
                continue
            in_loss = lap.lap_time_s - baseline
            out_loss = None
            if i + 1 < len(driver_laps) and driver_laps[i + 1].lap_time_s is not None:
                out_loss = driver_laps[i + 1].lap_time_s - baseline
            total = None
            if in_loss is not None and out_loss is not None:
                total = round(in_loss + out_loss, 4)
            stops.append(
                {
                    "pit_in_lap": lap.lap_number,
                    "in_lap_loss_s": round(in_loss, 4) if in_loss is not None else None,
                    "out_lap_loss_s": round(out_loss, 4) if out_loss is not None else None,
                    "total_loss_s": total,
                }
            )
        if not stops:
            raise ToolError(f"No pit stops recorded for {driver}", missing=True, code="missing_data", field="driver")
        totals = [s["total_loss_s"] for s in stops if s["total_loss_s"] is not None]
        return {
            "driver": driver,
            "median_clean_lap_s": round(baseline, 4),
            "stops": stops,
            "mean_total_loss_s": round(statistics.fmean(totals), 4) if totals else None,
        }


class GetWeatherTool(Tool):
    """Session weather records."""

    def __init__(self, context: SessionContext) -> None:
        self._context = context
        self.spec = _spec(
            "get_weather",
            "Return recorded weather during the session: air/track temperature, humidity, rainfall over time.",
            {},
            [],
            "1.0.0",
            {
                "type": "object",
                "properties": {
                    "n_records": {"type": "integer"},
                    "rainfall_records": {"type": "integer"},
                    "any_rain": OUT_BOOL,
                    "track_temp_min_c": OUT_LAP_TIME_S,
                    "track_temp_max_c": OUT_LAP_TIME_S,
                },
                "required": ["n_records", "rainfall_records", "any_rain", "track_temp_min_c", "track_temp_max_c"],
            },
            ["Weather granularity is per-minute samples; no per-lap interpolation."],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        records = self._context.adapter.weather(self._context._session)
        rain_rows = [w for w in records if w.rainfall]
        temps = [w.track_temp_c for w in records if w.track_temp_c is not None]
        return {
            "n_records": len(records),
            "rainfall_records": len(rain_rows),
            "any_rain": bool(rain_rows),
            "track_temp_min_c": min(temps) if temps else None,
            "track_temp_max_c": max(temps) if temps else None,
        }


class GetRaceControlTool(Tool):
    """Race control messages with lap mapping."""

    def __init__(self, context: SessionContext) -> None:
        self._context = context
        self.spec = _spec(
            "get_race_control",
            "Return race-control events (flags, safety car, investigations) with approximate lap numbers.",
            {"category": {"type": "string", "description": "Optional filter on category, e.g. 'Other', 'Flag'"}},
            [],
            "1.0.0",
            {
                "type": "object",
                "properties": {
                    "n_events": {"type": "integer"},
                    "events": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "lap": OUT_POSITION,
                                "category": OUT_COMPOUND,
                                "message": {"type": "string"},
                            },
                            "required": ["lap", "category", "message"],
                        },
                    },
                },
                "required": ["n_events", "events"],
            },
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        events = self._context.adapter.race_control(self._context._session)
        category = kwargs.get("category")
        out = []
        for e in events:
            if category and (e.category or "") != category:
                continue
            out.append({"lap": e.lap, "category": e.category, "message": e.message})
        return {"n_events": len(out), "events": out}


class GetPitStopsTool(Tool):
    """Pit stop records for one driver or all drivers."""

    def __init__(self, context: SessionContext) -> None:
        self._context = context
        self.spec = _spec(
            "get_pit_stops",
            "Return pit stops: driver, pit-in lap, compounds before/after.",
            {"driver": DRIVER_PARAM},
            [],
            "1.0.0",
            {
                "type": "object",
                "properties": {
                    "n_stops": {"type": "integer"},
                    "stops": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "driver": OUT_DRIVER,
                                "pit_in_lap": {"type": "integer"},
                                "compound_before": OUT_COMPOUND,
                                "compound_after": OUT_COMPOUND,
                            },
                            "required": ["driver", "pit_in_lap", "compound_before", "compound_after"],
                        },
                    },
                },
                "required": ["n_stops", "stops"],
            },
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        laps = self._context.laps
        stops = self._context.adapter.pit_stops(laps)
        driver = kwargs.get("driver")
        if driver:
            stops = [s for s in stops if s.driver == driver]
        return {
            "n_stops": len(stops),
            "stops": [
                {
                    "driver": s.driver,
                    "pit_in_lap": s.pit_in_lap,
                    "compound_before": s.compound_before,
                    "compound_after": s.compound_after,
                }
                for s in stops
            ],
        }


class SimulatePitTimingTool(Tool):
    """Counterfactual: what if pit timing changed?"""

    def __init__(self, context: SessionContext) -> None:
        self._context = context
        self.spec = _spec(
            "simulate_pit_timing",
            "Compare observed vs counterfactual pit timing for a driver; returns predicted race delta under stated assumptions.",
            {
                "driver": DRIVER_PARAM,
                "original_pit_lap": {"type": "integer", "description": "Observed pit-in lap"},
                "counterfactual_pit_lap": {"type": "integer", "description": "Alternative pit-in lap"},
                "pit_loss_s": {"type": "number", "description": "Total pit cycle loss in seconds"},
                "degradation_s_per_lap": {"type": "number", "description": "Linear tyre degradation rate (s/lap)"},
                "laps_remaining": {"type": "integer", "description": "Laps remaining in race"},
                "traffic_assumption_s_per_lap": {"type": "number", "description": "Traffic effect assumption (s/lap)", "default": 0.0},
            },
            ["driver", "original_pit_lap", "counterfactual_pit_lap", "pit_loss_s", "degradation_s_per_lap", "laps_remaining"],
            SIMULATOR_VERSION,
            {
                "type": "object",
                "properties": {
                    "intervention": {"type": "string"},
                    "predicted_delta_s": {"type": "number"},
                    "uncertainty_s": {"type": "number"},
                    "assumptions": {"type": "array", "items": {"type": "string"}},
                    "baseline_cost_s": {"type": "number"},
                    "counterfactual_cost_s": {"type": "number"},
                    "simulator_version": {"type": "string"},
                },
                "required": ["intervention", "predicted_delta_s", "uncertainty_s", "assumptions", "baseline_cost_s", "counterfactual_cost_s", "simulator_version"],
            },
            ["Deterministic model; not a physics simulator. Assumptions are explicit; uncertainty is heuristic."],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        return simulate_pit_timing(
            laps=self._context.laps,
            driver=kwargs["driver"],
            original_pit_lap=int(kwargs["original_pit_lap"]),
            counterfactual_pit_lap=int(kwargs["counterfactual_pit_lap"]),
            pit_loss_s=float(kwargs["pit_loss_s"]),
            degradation_s_per_lap=float(kwargs["degradation_s_per_lap"]),
            laps_remaining=int(kwargs["laps_remaining"]),
            traffic_assumption_s_per_lap=float(kwargs.get("traffic_assumption_s_per_lap", 0.0)),
        )


class SimulateCompoundChangeTool(Tool):
    """Counterfactual: what if a different tyre compound was used?"""

    def __init__(self, context: SessionContext) -> None:
        self._context = context
        self.spec = _spec(
            "simulate_compound_change",
            "Compare observed vs counterfactual tyre compound for a driver's stint; returns predicted pace delta under stated assumptions.",
            {
                "driver": DRIVER_PARAM,
                "original_compound": {"type": "string", "description": "Observed compound (SOFT/MEDIUM/HARD)"},
                "counterfactual_compound": {"type": "string", "description": "Alternative compound (SOFT/MEDIUM/HARD)"},
                "stint_start_lap": {"type": "integer", "description": "First lap of the stint window"},
                "stint_end_lap": {"type": "integer", "description": "Last lap of the stint window"},
                "degradation_s_per_lap": {"type": "number", "description": "Linear tyre degradation rate (s/lap)"},
                "laps_remaining": {"type": "integer", "description": "Laps remaining in race"},
            },
            ["driver", "original_compound", "counterfactual_compound", "stint_start_lap", "stint_end_lap", "degradation_s_per_lap", "laps_remaining"],
            SIMULATOR_VERSION,
            {
                "type": "object",
                "properties": {
                    "intervention": {"type": "string"},
                    "predicted_delta_s": {"type": "number"},
                    "uncertainty_s": {"type": "number"},
                    "assumptions": {"type": "array", "items": {"type": "string"}},
                    "compound_delta_per_lap_s": {"type": "number"},
                    "stint_laps_count": {"type": "integer"},
                    "simulator_version": {"type": "string"},
                },
                "required": ["intervention", "predicted_delta_s", "uncertainty_s", "assumptions", "compound_delta_per_lap_s", "stint_laps_count", "simulator_version"],
            },
            ["Deterministic model; compound offsets are fixed assumptions. Degradation assumed equal for both compounds."],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        return simulate_compound_change(
            laps=self._context.laps,
            driver=kwargs["driver"],
            original_compound=kwargs["original_compound"],
            counterfactual_compound=kwargs["counterfactual_compound"],
            stint_start_lap=int(kwargs["stint_start_lap"]),
            stint_end_lap=int(kwargs["stint_end_lap"]),
            degradation_s_per_lap=float(kwargs["degradation_s_per_lap"]),
            laps_remaining=int(kwargs["laps_remaining"]),
        )


class CompareStrategyScenariosTool(Tool):
    """Counterfactual: compare multiple strategy scenarios."""

    def __init__(self, context: SessionContext) -> None:
        self._context = context
        self.spec = _spec(
            "compare_strategy_scenarios",
            "Compare multiple pit/compound strategy scenarios against a baseline; returns ranked deltas.",
            {
                "driver": DRIVER_PARAM,
                "scenarios": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "pit_laps": {"type": "array", "items": {"type": "integer"}},
                            "compounds": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["pit_laps", "compounds"],
                    },
                },
                "pit_loss_s": {"type": "number", "description": "Total pit cycle loss in seconds"},
                "degradation_s_per_lap": {"type": "number", "description": "Linear tyre degradation rate (s/lap)"},
                "laps_remaining": {"type": "integer", "description": "Laps remaining in race"},
                "traffic_assumption_s_per_lap": {"type": "number", "description": "Traffic effect assumption (s/lap)", "default": 0.0},
            },
            ["driver", "scenarios", "pit_loss_s", "degradation_s_per_lap", "laps_remaining"],
            SIMULATOR_VERSION,
            {
                "type": "object",
                "properties": {
                    "baseline_cost_s": {"type": "number"},
                    "scenarios": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "scenario_id": {"type": "string"},
                                "intervention": {"type": "string"},
                                "predicted_delta_s": {"type": "number"},
                                "uncertainty_s": {"type": "number"},
                            },
                            "required": ["scenario_id", "intervention", "predicted_delta_s", "uncertainty_s"],
                        },
                    },
                    "assumptions": {"type": "array", "items": {"type": "string"}},
                    "simulator_version": {"type": "string"},
                },
                "required": ["baseline_cost_s", "scenarios", "assumptions", "simulator_version"],
            },
            ["Deterministic model; scenarios ranked by predicted delta. Not a full physics simulation."],
        )

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        return compare_strategy_scenarios(
            laps=self._context.laps,
            driver=kwargs["driver"],
            scenarios=kwargs["scenarios"],
            pit_loss_s=float(kwargs["pit_loss_s"]),
            degradation_s_per_lap=float(kwargs["degradation_s_per_lap"]),
            laps_remaining=int(kwargs["laps_remaining"]),
            traffic_assumption_s_per_lap=float(kwargs.get("traffic_assumption_s_per_lap", 0.0)),
        )


def build_default_registry(context: SessionContext) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in (
        GetSessionTool(context),
        GetLapsTool(context),
        GetStintsTool(context),
        AnalyzeTyreDegradationTool(context),
        AnalyzeTrafficTool(context),
        CompareSectorsTool(context),
        CompareDriverPaceTool(context),
        DetectPaceAnomalyTool(context),
        AnalyzePitLossTool(context),
        GetWeatherTool(context),
        GetRaceControlTool(context),
        GetPitStopsTool(context),
        SimulatePitTimingTool(context),
        SimulateCompoundChangeTool(context),
        CompareStrategyScenariosTool(context),
    ):
        registry.register(tool)
    return registry
