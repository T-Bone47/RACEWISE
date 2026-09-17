"""FastF1 adapter: normalizes provider data into canonical domain schemas.

The rest of the system never touches FastF1 objects — only these canonical
schemas. This keeps the data layer swappable (OpenF1 adapter can be added
behind the same interface).
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

import fastf1
import pandas as pd

from racewise.domain.schemas import (
    Lap,
    PitStop,
    RaceControlEvent,
    SessionSummary,
    Stint,
    WeatherRecord,
)

logger = logging.getLogger(__name__)

_CACHE_ENABLED = False


def enable_cache(cache_dir: Optional[str] = None) -> None:
    global _CACHE_ENABLED
    if _CACHE_ENABLED:
        return
    path = Path(cache_dir) if cache_dir else Path.home() / ".racewise" / "fastf1-cache"
    path.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(path))
    _CACHE_ENABLED = True


def _timedelta_to_s(value: object) -> Optional[float]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value.total_seconds())
    except AttributeError:
        return None


def _num(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class FastF1Adapter:
    """Loads historical sessions and normalizes to canonical schemas."""

    def __init__(self, cache_dir: Optional[str] = None) -> None:
        enable_cache(cache_dir)

    def load_session(self, year: int, event: str, session_type: str = "R") -> fastf1.sessions.Session:
        session = fastf1.get_session(year, event, session_type)
        session.load(laps=True, telemetry=False, weather=True, messages=True)
        return session

    def session_summary(self, session: fastf1.sessions.Session) -> SessionSummary:
        laps = session.laps
        return SessionSummary(
            session_key=f"{session.event.Year}-{session.event.EventName.replace(' ', '')}-{session.name}",
            event_name=str(session.event.EventName),
            session_type=str(session.name),
            date=session.date.to_pydatetime() if session.date is not None else None,
            circuit=str(session.event.Location) if session.event.Location is not None else None,
            total_laps=int(laps.LapNumber.max()) if not laps.empty else None,
            drivers=sorted(laps.Driver.unique().tolist()) if not laps.empty else [],
        )

    def laps(self, session: fastf1.sessions.Session) -> list[Lap]:
        df = session.laps
        out: list[Lap] = []
        if df is None or df.empty:
            return out
        for row in df.itertuples(index=False):
            lap_time_s = _timedelta_to_s(row.LapTime)
            pit_in = row.PitInTime is not None and pd.notna(row.PitInTime)
            pit_out = row.PitOutTime is not None and pd.notna(row.PitOutTime)
            out.append(
                Lap(
                    session_key="",
                    driver=str(row.Driver),
                    driver_number=_num(row.DriverNumber) and int(_num(row.DriverNumber)),
                    team=str(row.Team) if row.Team is not None and pd.notna(row.Team) else None,
                    lap_number=int(row.LapNumber),
                    lap_time_s=lap_time_s,
                    sector_1_s=_timedelta_to_s(row.Sector1Time),
                    sector_2_s=_timedelta_to_s(row.Sector2Time),
                    sector_3_s=_timedelta_to_s(row.Sector3Time),
                    compound=str(row.Compound) if row.Compound is not None and pd.notna(row.Compound) else None,
                    tyre_life=int(_num(row.TyreLife)) if _num(row.TyreLife) is not None else None,
                    stint=int(_num(row.Stint)) if _num(row.Stint) is not None else None,
                    is_pit_in_lap=bool(pit_in),
                    is_pit_out_lap=bool(pit_out),
                    track_status=str(row.TrackStatus) if row.TrackStatus is not None and pd.notna(row.TrackStatus) else None,
                    position=int(_num(row.Position)) if _num(row.Position) is not None else None,
                    is_accurate=bool(row.IsAccurate) if row.IsAccurate is not None and pd.notna(row.IsAccurate) else None,
                    deleted=bool(row.Deleted) if row.Deleted is not None and pd.notna(row.Deleted) else False,
                )
            )
        return out

    def stints(self, laps: list[Lap]) -> list[Stint]:
        by_driver_stint: dict[tuple[str, int], list[Lap]] = {}
        for lap in laps:
            if lap.stint is None:
                continue
            key = (lap.driver, lap.stint)
            by_driver_stint.setdefault(key, []).append(lap)
        out: list[Stint] = []
        for (driver, stint_number), group in sorted(by_driver_stint.items()):
            lap_numbers = [lap.lap_number for lap in group]
            compounds = {lap.compound for lap in group if lap.compound}
            out.append(
                Stint(
                    session_key=group[0].session_key,
                    driver=driver,
                    stint_number=stint_number,
                    compound=sorted(compounds)[0] if compounds else None,
                    lap_start=min(lap_numbers),
                    lap_end=max(lap_numbers),
                    lap_count=len(lap_numbers),
                )
            )
        return out

    def pit_stops(self, laps: list[Lap]) -> list[PitStop]:
        by_driver: dict[str, list[Lap]] = {}
        for lap in laps:
            by_driver.setdefault(lap.driver, []).append(lap)
        stops: list[PitStop] = []
        for driver, driver_laps in by_driver.items():
            driver_laps.sort(key=lambda lap: lap.lap_number)
            for i, lap in enumerate(driver_laps):
                if not lap.is_pit_in_lap:
                    continue
                nxt = driver_laps[i + 1] if i + 1 < len(driver_laps) else None
                stops.append(
                    PitStop(
                        session_key=lap.session_key,
                        driver=driver,
                        pit_in_lap=lap.lap_number,
                        pit_out_lap=nxt.lap_number if nxt is not None and nxt.is_pit_out_lap else None,
                        compound_before=lap.compound,
                        compound_after=nxt.compound if nxt is not None else None,
                    )
                )
        return stops

    def weather(self, session: fastf1.sessions.Session) -> list[WeatherRecord]:
        out: list[WeatherRecord] = []
        weather = getattr(session, "weather_data", None)
        if weather is None or len(weather) == 0:
            return out
        for _, row in weather.iterrows():
            rain = False
            for key in ("Rainfall", "rainfall"):
                if key in row and pd.notna(row[key]) and bool(row[key]):
                    rain = True
            out.append(
                WeatherRecord(
                    session_key="",
                    timestamp=row.Time.to_pydatetime() if hasattr(row.get("Time", None), "to_pydatetime") else None,
                    air_temp_c=_num(row.get("AirTemp")),
                    track_temp_c=_num(row.get("TrackTemp")),
                    humidity=_num(row.get("Humidity")),
                    rainfall=rain,
                )
            )
        return out

    def race_control(self, session: fastf1.sessions.Session) -> list[RaceControlEvent]:
        out: list[RaceControlEvent] = []
        messages = getattr(session, "race_control_messages", None)
        if messages is None or len(messages) == 0:
            return out
        for _, row in messages.iterrows():
            lap_value = row.get("Lap", None)
            lap_number: Optional[int] = None
            if lap_value is not None and pd.notna(lap_value):
                try:
                    lap_number = int(lap_value)
                except (TypeError, ValueError):
                    lap_number = None
            out.append(
                RaceControlEvent(
                    session_key="",
                    timestamp=row.Time.to_pydatetime() if hasattr(row.get("Time", None), "to_pydatetime") else None,
                    category=str(row.get("Category", "")) or None,
                    message=str(row.get("Message", "")),
                    lap=lap_number,
                )
            )
        return out


@lru_cache(maxsize=8)
def get_adapter(cache_dir: Optional[str] = None) -> FastF1Adapter:
    return FastF1Adapter(cache_dir)
