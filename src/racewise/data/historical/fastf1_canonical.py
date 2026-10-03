"""FastF1 → canonical modern engineering data (Phase 6A).

Ingests REAL FastF1 datasets into the existing canonical store:

- canonical_stints        (from lap dataframe Stint/Compound/TyreLife columns)
- canonical_weather       (from session.weather_data)
- canonical_race_control  (from session.race_control_messages)

Design rules (mirroring Phase 5.5B):
- Every id is DETERMINISTIC (sha1 of stable source keys) so re-running
  ingestion is idempotent (upsert on the primary key).
- Only fields FastF1 actually provides are mapped. Absent fields stay NULL.
- Sessions are NEVER created here: F1DB is the identity authority for
  races/sessions. FastF1 rows attach to existing canonical sessions by
  (season, round, session type). Unmatched sessions are skipped with a
  warning, never invented.
- Driver identity: FastF1 3-letter codes are ambiguous across history, so
  resolution is scoped to the session's season using actual canonical
  participation. Ambiguous codes are skipped (no guessing).
- Provider provenance on every row: provider='fastf1', source_id,
  source_version (fastf1 library version), transformation version.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from racewise.data._lazy import LazyModule

# Deferred imports - see racewise.data._lazy.
fastf1 = LazyModule("fastf1")
pd = LazyModule("pandas")

from racewise.data.historical.f1db_canonical import (
    CanonicalStore,
    F1DBCanonicalizer,
    _stable_id,
    _to_int,
    _to_str,
)
from racewise.data.historical.telemetry_policy import TelemetryPolicy

logger = logging.getLogger(__name__)

FASTF1_PROVIDER = "fastf1"
FASTF1_TRANSFORMATION_VERSION = "1.0"

# FastF1 session code -> canonical session type (exactly the types F1DB defines).
SESSION_CODE_MAP: dict[str, str] = {
    "R": "RACE",
    "Q": "QUALIFYING",
    "S": "SPRINT",
    "SQ": "SPRINT_QUALIFYING",
    "FP1": "FREE_PRACTICE_1",
    "FP2": "FREE_PRACTICE_2",
    "FP3": "FREE_PRACTICE_3",
    "FP4": "FREE_PRACTICE_4",
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _float_or_none(value: Any) -> Optional[float]:
    try:
        if value is None or pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _timedelta_to_s(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, timedelta):
        return float(value.total_seconds())
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return float(value.total_seconds())
    except AttributeError:
        return None


def _elapsed_s(value: Any) -> Optional[float]:
    """Session-relative offset in seconds (directly from the source timedelta)."""
    if isinstance(value, timedelta):
        return float(value.total_seconds())
    return None


def _to_iso_timestamp(value: Any) -> Optional[str]:
    """Normalize FastF1 timestamps to ISO-8601 strings (native precision).

    Absolute datetimes -> ISO datetime. Session-relative offsets (FastF1's
    weather Time column is a timedelta) -> ISO-8601 duration (e.g. PT45.438S),
    the faithful representation of what the source provides. Nothing is
    anchored to an invented base time.
    """
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, timedelta):
        total = value.total_seconds()
        sign = "-" if total < 0 else ""
        total = abs(total)
        hours, rem = divmod(total, 3600)
        minutes, seconds = divmod(rem, 60)
        h = f"{int(hours)}H" if hours else ""
        m = f"{int(minutes)}M" if minutes else ""
        s = f"{seconds:.6f}".rstrip("0").rstrip(".") if seconds else ("0" if not (h or m) else "")
        return f"{sign}PT{h}{m}{s}S"
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


class FastF1Canonicalizer:
    """Canonicalizes FastF1 session data into the existing canonical store."""

    def __init__(self, store: CanonicalStore, source_version: Optional[str] = None) -> None:
        self.store = store
        self.source_version = source_version or str(getattr(fastf1, "__version__", "unknown"))
        self._f1db = F1DBCanonicalizer(store)  # id helpers only
        self._driver_cache: dict[tuple[str, int], Optional[str]] = {}

    # -- identity ------------------------------------------------------------

    def resolve_session(self, year: int, round_num: int, session_code: str) -> Optional[tuple[str, str]]:
        """Map (year, round, FastF1 code) to an EXISTING canonical session.

        Returns (session_id, session_type) or None when F1DB does not
        represent this session - FastF1 rows are never attached to invented
        sessions.
        """
        session_type = SESSION_CODE_MAP.get(str(session_code).upper())
        if session_type is None:
            logger.warning(f"Unknown FastF1 session code {session_code!r}; skipping")
            return None
        race_id = self._f1db.race_id(year, round_num)
        session_id = self._f1db.session_id(race_id, session_type)
        with self.store._conn() as conn:
            row = conn.execute(
                "SELECT session_id FROM canonical_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            logger.warning(
                f"No canonical session for {year} R{round_num} {session_type} "
                "(F1DB does not represent it); FastF1 data skipped"
            )
            return None
        return session_id, session_type

    def resolve_driver(self, code: str, season: int) -> Optional[str]:
        """Resolve a FastF1 3-letter code to a canonical driver, season-scoped.

        Codes are not unique across history (e.g. 'SCH'), so candidates are
        narrowed by ACTUAL canonical participation in that season. Still
        ambiguous -> None (no fabrication).
        """
        key = (code, season)
        if key in self._driver_cache:
            return self._driver_cache[key]
        resolved: Optional[str] = None
        with self.store._conn() as conn:
            candidates = [
                r["driver_id"]
                for r in conn.execute(
                    "SELECT driver_id FROM canonical_drivers WHERE code = ? ORDER BY driver_id",
                    (code,),
                )
            ]
            if len(candidates) == 1:
                resolved = candidates[0]
            elif len(candidates) > 1:
                placeholders = ",".join("?" for _ in candidates)
                participating = [
                    r["driver_id"]
                    for r in conn.execute(
                        f"""SELECT DISTINCT r.driver_id FROM canonical_results r
                            JOIN canonical_sessions s ON s.session_id = r.session_id
                            JOIN canonical_races ra ON ra.race_id = s.race_id
                            WHERE ra.season = ? AND r.driver_id IN ({placeholders})
                            ORDER BY r.driver_id""",
                        (season, *candidates),
                    )
                ]
                if len(participating) == 1:
                    resolved = participating[0]
                elif len(participating) > 1:
                    logger.warning(
                        f"Ambiguous driver code {code!r} in season {season} "
                        f"({len(participating)} candidates); rows skipped, not guessed"
                    )
        self._driver_cache[key] = resolved
        return resolved

    # -- stints --------------------------------------------------------------

    def ingest_stints(self, laps_df: pd.DataFrame, session_id: str, season: int,
                      event_ref: str) -> int:
        """Ingest stints derived from the ACTUAL FastF1 lap dataframe.

        Mapped fields (verified FastF1 3.8.3 columns): Driver, Stint,
        Compound, TyreLife, LapNumber, FreshTyre. Lap start/end are computed
        from actual lap rows. Compound sets spanning more than one value are
        preserved as a '|' joined set (mixed representation), never collapsed
        to a guess. FreshTyre and TyreLife have no canonical columns yet and
        are documented in docs/FASTF1_MODERN_DATA.md rather than invented.
        """
        required = {"Driver", "Stint", "LapNumber"}
        if laps_df is None or laps_df.empty or not required.issubset(laps_df.columns):
            return 0
        now = _utcnow_iso()
        rows: list[tuple] = []
        grouped = laps_df.dropna(subset=["Stint"]).groupby(["Driver", "Stint"], sort=True)
        for (code, stint_number), group in grouped:
            driver_id = self.resolve_driver(str(code), season)
            if driver_id is None:
                continue
            lap_numbers = sorted({int(n) for n in group["LapNumber"].dropna().tolist()})
            if not lap_numbers:
                continue
            compounds = sorted({
                (str(c) if str(c) != "None" else "UNKNOWN")
                for c in group["Compound"].dropna().tolist()
            } - {""})
            compound = "|".join(compounds) if compounds else None
            stint_number = int(stint_number)
            lap_start, lap_end = lap_numbers[0], lap_numbers[-1]
            # TyreLife = laps completed on this tyre within the stint (source field).
            tyre_life = None
            if "TyreLife" in group.columns:
                life = group["TyreLife"].dropna()
                tyre_life = int(life.max()) if len(life) else None
            stint_id = _stable_id(FASTF1_PROVIDER, "stint", session_id, str(code), stint_number)
            rows.append((
                stint_id, session_id, driver_id, stint_number, compound,
                lap_start, lap_end, len(lap_numbers),
                FASTF1_PROVIDER, f"{event_ref}:{code}:{stint_number}", self.source_version,
                now, now,
            ))
            # Preserve source TyreLife as lap-level facts alongside the stint.
            self._upsert_stint_tyre_life(laps_df, session_id, driver_id, code, stint_number, now)
        if rows:
            self.store.execute_batch(
                """INSERT INTO canonical_stints (stint_id, session_id, driver_id, stint_number,
                   compound, lap_start, lap_end, lap_count, source_provider, source_id,
                   source_version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(stint_id) DO UPDATE SET
                     compound = excluded.compound, lap_start = excluded.lap_start,
                     lap_end = excluded.lap_end, lap_count = excluded.lap_count,
                     source_version = excluded.source_version, updated_at = excluded.updated_at""",
                rows,
            )
        return len(rows)

    def _upsert_stint_tyre_life(self, laps_df: pd.DataFrame, session_id: str,
                                driver_id: str, code: str, stint_number: int, now: str) -> None:
        """Attach FastF1 TyreLife/track-status as lap-level rows.

        Only rows FastF1 actually provides: lap time, sectors, compound,
        tyre life, stint, pit in/out, track status, is_accurate, deleted.
        These NEVER overwrite F1DB fastest-lap rows: provider differs, so ids
        differ and both are preserved (merge policy: F1DB historical facts +
        FastF1 per-lap facts coexist).
        """
        sub = laps_df[
            (laps_df["Driver"] == code) & (laps_df["Stint"] == stint_number)
        ]
        if sub.empty:
            return
        rows: list[tuple] = []
        for _, lap in sub.iterrows():
            lap_number = _float_or_none(lap.get("LapNumber"))
            if lap_number is None:
                continue
            lap_number = int(lap_number)
            lap_time_id = _stable_id(FASTF1_PROVIDER, "lap", session_id, str(code), lap_number)
            compound = _to_str(lap.get("Compound"))
            tyre_life = _float_or_none(lap.get("TyreLife"))
            tyre_life_i = int(tyre_life) if tyre_life is not None else None
            stint = _float_or_none(lap.get("Stint"))
            position = _float_or_none(lap.get("Position"))
            is_pit_in = lap.get("PitInTime") is not None and pd.notna(lap.get("PitInTime"))
            is_pit_out = lap.get("PitOutTime") is not None and pd.notna(lap.get("PitOutTime"))
            deleted_raw = lap.get("Deleted")
            deleted = bool(deleted_raw) if deleted_raw is not None and pd.notna(deleted_raw) else False
            is_accurate_raw = lap.get("IsAccurate")
            is_accurate = (
                bool(is_accurate_raw) if is_accurate_raw is not None and pd.notna(is_accurate_raw) else None
            )
            rows.append((
                lap_time_id, session_id, driver_id, lap_number,
                int(position) if position is not None else None,
                _timedelta_to_s(lap.get("LapTime")),
                _timedelta_to_s(lap.get("Sector1Time")),
                _timedelta_to_s(lap.get("Sector2Time")),
                _timedelta_to_s(lap.get("Sector3Time")),
                compound, tyre_life_i,
                int(stint) if stint is not None else None,
                bool(is_pit_in), bool(is_pit_out),
                _to_str(lap.get("TrackStatus")), is_accurate, deleted,
                FASTF1_PROVIDER, f"{_to_str(code)}:{lap_number}", self.source_version,
                now, now,
            ))
        if rows:
            self.store.execute_batch(
                """INSERT INTO canonical_lap_times (lap_time_id, session_id, driver_id, lap_number,
                   position, time_s, sector1_s, sector2_s, sector3_s, compound, tyre_life, stint,
                   is_pit_in_lap, is_pit_out_lap, track_status, is_accurate, deleted,
                   source_provider, source_id, source_version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(lap_time_id) DO UPDATE SET
                     time_s = excluded.time_s, sector1_s = excluded.sector1_s,
                     sector2_s = excluded.sector2_s, sector3_s = excluded.sector3_s,
                     compound = excluded.compound, tyre_life = excluded.tyre_life,
                     position = excluded.position, is_pit_in_lap = excluded.is_pit_in_lap,
                     is_pit_out_lap = excluded.is_pit_out_lap, track_status = excluded.track_status,
                     is_accurate = excluded.is_accurate, deleted = excluded.deleted,
                     source_version = excluded.source_version, updated_at = excluded.updated_at""",
                rows,
            )

    # -- weather -------------------------------------------------------------

    def ingest_weather(self, weather_df: pd.DataFrame, session_id: str, event_ref: str) -> int:
        """Ingest session.weather_data with native precision.

        Verified FastF1 3.8.3 columns: Time, AirTemp, Humidity, Pressure,
        Rainfall, TrackTemp, WindDirection, WindSpeed. Rows are keyed by
        ordered observation index, so re-ingestion is idempotent. No
        interpolation: gaps between observations remain gaps.
        """
        if weather_df is None or len(weather_df) == 0:
            return 0
        now = _utcnow_iso()
        rows: list[tuple] = []
        for idx, row in enumerate(weather_df.itertuples(index=False)):
            mapping = dict(zip(weather_df.columns, row))
            timestamp = _to_iso_timestamp(mapping.get("Time"))
            rainfall = mapping.get("Rainfall")
            rainfall_bool = bool(rainfall) if rainfall is not None and pd.notna(rainfall) else None
            wind_dir = _float_or_none(mapping.get("WindDirection"))
            wind_speed = _float_or_none(mapping.get("WindSpeed"))
            weather_id = _stable_id(FASTF1_PROVIDER, "weather", session_id, idx)
            rows.append((
                weather_id, session_id, timestamp, _elapsed_s(mapping.get("Time")),
                _float_or_none(mapping.get("AirTemp")),
                _float_or_none(mapping.get("TrackTemp")),
                _float_or_none(mapping.get("Humidity")),
                rainfall_bool,
                int(wind_dir) if wind_dir is not None else None,
                wind_speed,
                _float_or_none(mapping.get("Pressure")),
                FASTF1_PROVIDER, f"{event_ref}:wx:{idx}", self.source_version,
                now, now,
            ))
        self.store.execute_batch(
            """INSERT INTO canonical_weather (weather_id, session_id, timestamp, elapsed_s,
               air_temp_c, track_temp_c, humidity, rainfall, wind_direction, wind_speed,
               pressure, source_provider, source_id, source_version, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(weather_id) DO UPDATE SET
                 timestamp = excluded.timestamp, elapsed_s = excluded.elapsed_s,
                 air_temp_c = excluded.air_temp_c,
                 track_temp_c = excluded.track_temp_c, humidity = excluded.humidity,
                 rainfall = excluded.rainfall, wind_direction = excluded.wind_direction,
                 wind_speed = excluded.wind_speed, pressure = excluded.pressure,
                 source_version = excluded.source_version, updated_at = excluded.updated_at""",
            rows,
        )
        return len(rows)

    # -- race control ----------------------------------------------------------

    def ingest_race_control(self, rc_df: pd.DataFrame, session_id: str, event_ref: str) -> int:
        """Ingest session.race_control_messages.

        Verified FastF1 3.8.3 columns: Time, Category, Message, Status, Flag,
        Scope, Sector, RacingNumber, Lap. Canonical table stores
        category/message/lap/timestamp; Flag/Scope/Sector detail is embedded
        in the message text by the source and preserved verbatim there.        The feed repeats some events verbatim at the same timestamp (observed:
        2018 'RISK OF RAIN ...' twice; 2023 Hungary 'YELLOW FLAG...' re-delivered
        at the same Time with a different Lap value - the message text carries
        its own 'TIMED AT' stamp, so the repeat is a stale re-delivery, not a
        distinct event). Dedup key is therefore (timestamp, category, message):
        event identity. Lap from the FIRST delivery is kept.

        event_id is content-derived (not index-derived) so identity is stable
        across runs regardless of dedup decisions - re-ingestion upserts the
        same rows (true idempotency). Repeated-but-distinct events at different
        timestamps are never merged.
        """
        if rc_df is None or len(rc_df) == 0:
            return 0
        now = _utcnow_iso()
        rows: list[tuple] = []
        seen_content: set[tuple] = set()
        for idx, row in enumerate(rc_df.itertuples(index=False)):
            mapping = dict(zip(rc_df.columns, row))
            timestamp = _to_iso_timestamp(mapping.get("Time"))
            category = _to_str(mapping.get("Category"))
            message = _to_str(mapping.get("Message"))
            lap = _float_or_none(mapping.get("Lap"))
            content_key = (timestamp, category, message)
            if content_key in seen_content:
                continue  # source re-delivery of the same event, not distinct
            seen_content.add(content_key)
            event_id = _stable_id(FASTF1_PROVIDER, "rc", session_id, timestamp, category, message)
            rows.append((
                event_id, session_id,
                timestamp,
                category, message,
                int(lap) if lap is not None else None,
                FASTF1_PROVIDER, f"{event_ref}:rc:{idx}", self.source_version,
                now, now,
            ))
        self.store.execute_batch(
            """INSERT INTO canonical_race_control (event_id, session_id, timestamp, category,
               message, lap, source_provider, source_id, source_version, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(event_id) DO UPDATE SET
                 timestamp = excluded.timestamp, category = excluded.category,
                 message = excluded.message, lap = excluded.lap,
                 source_version = excluded.source_version, updated_at = excluded.updated_at""",
            rows,
        )
        return len(rows)

    # -- telemetry (Phase 6C, bounded) -----------------------------------------

    # Verified FastF1 3.8.3 car_data channel -> canonical signal name.
    # Brake is boolean in the source (True = braking) -> 1/0. nGear and DRS
    # are integer codes (DRS 8/10/12/14 = enabled states, per FastF1 docs).
    # All channels share one time index -> one wide row per sample.
    TELEMETRY_CHANNEL_MAP: dict[str, str] = {
        "Speed": "speed",
        "Throttle": "throttle",
        "Brake": "brake",
        "nGear": "gear",
        "RPM": "rpm",
        "DRS": "drs",
    }

    def _top_classified_driver_ids(self, season: int, round_num: int, limit: int) -> list[str]:
        """Top-N classified finishers from canonical results (deterministic)."""
        with self.store._conn() as conn:
            rows = conn.execute(
                """SELECT r.driver_id FROM canonical_results r
                   JOIN canonical_sessions s ON s.session_id = r.session_id
                   JOIN canonical_races ra ON ra.race_id = s.race_id
                   WHERE ra.season = ? AND ra.round = ? AND s.session_type = 'RACE'
                     AND r.position IS NOT NULL
                   ORDER BY r.position LIMIT ?""",
                (season, round_num, limit),
            ).fetchall()
        return [r["driver_id"] for r in rows]

    def _select_telemetry_laps(self, laps_df: pd.DataFrame, max_laps: int) -> list[int]:
        """Evenly spaced clean timed lap positions (deterministic selection)."""
        candidates = [
            i for i, row in enumerate(laps_df.itertuples(index=False))
            if getattr(row, "LapTime", None) is not None
            and not pd.isna(getattr(row, "LapTime", None))
            and not pd.isna(getattr(row, "Stint", pd.NA))
        ]
        if not candidates or max_laps is None:
            return candidates
        if len(candidates) <= max_laps:
            return candidates
        step = (len(candidates) - 1) / (max_laps - 1)
        picked = {int(round(i * step)) for i in range(max_laps)}
        return [candidates[j] for j in sorted(picked)]

    def ingest_telemetry(
        self,
        ff1_session: Any,
        session_id: str,
        season: int,
        round_num: int,
        policy: TelemetryPolicy,
    ) -> dict[str, Any]:
        """Ingest bounded car-data telemetry for selected drivers and laps.

        Scope is policy-gated (default OFF): top-N classified finishers x up to
        max_laps_per_driver clean laps x the six verified car-data signals.
        Time model: session-relative seconds (source SessionTime, same
        convention as weather elapsed_s) plus lap-relative seconds
        (documented calculation: SessionTime - LapStartTime). No absolute
        timestamps are invented; no distance channel (positional data
        deferred until a consumer requires it).

        Identity: sha1(provider, session, driver, lap, signal, time in ms) -
        deterministic and idempotent under upsert.
        """
        stats: dict[str, Any] = {
            "drivers": 0, "laps": 0, "samples": 0,
            "skipped_identity": 0, "truncated_to_cap": False,
        }
        if ff1_session.laps is None or len(ff1_session.laps) == 0:
            return stats
        # Opt-in path: car data is not loaded by the default adapter call
        # (telemetry=False). Loading here keeps the default OFF everywhere else.
        ff1_session.load(laps=True, telemetry=True, weather=False, messages=False)

        # Canonical driver_ids in scope -> FastF1 codes via season-scoped resolver.
        target_ids = self._top_classified_driver_ids(
            season, round_num, policy.max_drivers_per_session or 2
        )
        if not target_ids:
            return stats
        id_by_code: dict[str, str] = {}
        for code in ff1_session.laps["Driver"].dropna().unique():
            driver_id = self.resolve_driver(str(code), season)
            if driver_id in target_ids:
                id_by_code[str(code)] = driver_id
        if not id_by_code:
            stats["skipped_identity"] = len(target_ids)
            return stats

        now = _utcnow_iso()
        rows: list[tuple] = []
        cap = policy.max_samples_per_session
        signals = set(policy.signals)
        for code, driver_id in sorted(id_by_code.items()):
            driver_laps = ff1_session.laps.pick_drivers(code)
            if driver_laps is None or len(driver_laps) == 0:
                continue
            picked = self._select_telemetry_laps(driver_laps, policy.max_laps_per_driver)
            stats["drivers"] += 1
            for lap_idx in picked:
                lap = driver_laps.iloc[lap_idx]
                lap_number = int(lap["LapNumber"])
                lap_start = lap["LapStartTime"]
                try:
                    cd = lap.get_car_data()
                except Exception as exc:  # noqa: BLE001 - per-lap isolation
                    logger.warning(f"telemetry: lap {lap_number} car_data failed: {exc}")
                    continue
                if cd is None or len(cd) == 0:
                    continue
                stats["laps"] += 1
                for t_row in cd.itertuples(index=False):
                    st = getattr(t_row, "SessionTime", None)
                    if st is None or pd.isna(st):
                        continue
                    elapsed_s = round(st.total_seconds(), 4)
                    try:
                        lap_rel_s = round((st - lap_start).total_seconds(), 4)
                    except Exception:  # noqa: BLE001 - LapStartTime may be NaT
                        continue
                    values: dict[str, Optional[float]] = {}
                    for channel, signal in self.TELEMETRY_CHANNEL_MAP.items():
                        if signal not in signals:
                            continue
                        raw = getattr(t_row, channel, None)
                        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
                            values[signal] = None
                            continue
                        values[signal] = float(bool(raw)) if channel == "Brake" else float(raw)
                    if all(v is None for v in values.values()):
                        continue
                    telemetry_id = _stable_id(
                        FASTF1_PROVIDER, "tel", session_id, driver_id,
                        lap_number, round(elapsed_s, 3),
                    )
                    rows.append((
                        telemetry_id, session_id, driver_id, lap_number,
                        elapsed_s, lap_rel_s,
                        values.get("speed"), values.get("throttle"),
                        int(values["brake"]) if values.get("brake") is not None else None,
                        int(values["gear"]) if values.get("gear") is not None else None,
                        values.get("rpm"),
                        int(values["drs"]) if values.get("drs") is not None else None,
                        FASTF1_PROVIDER,
                        f"{season}-R{round_num}:{code}:L{lap_number}",
                        self.source_version, now, now,
                    ))
                if len(rows) > cap:
                    rows = rows[:cap]
                    stats["truncated_to_cap"] = True
                    break
            if stats["truncated_to_cap"]:
                break

        if rows:
            self.store.execute_batch(
                """INSERT INTO canonical_telemetry (telemetry_id, session_id, driver_id,
                   lap_number, time_elapsed_s, lap_time_s, speed_kmh, throttle_pct,
                   brake, gear, rpm, drs,
                   source_provider, source_id, source_version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(telemetry_id) DO UPDATE SET
                     speed_kmh = excluded.speed_kmh, throttle_pct = excluded.throttle_pct,
                     brake = excluded.brake, gear = excluded.gear, rpm = excluded.rpm,
                     drs = excluded.drs, lap_time_s = excluded.lap_time_s,
                     source_version = excluded.source_version, updated_at = excluded.updated_at""",
                rows,
            )
        stats["samples"] = len(rows)
        logger.info(
            f"Telemetry ingested for {season}-R{round_num}: drivers={stats['drivers']} "
            f"laps={stats['laps']} samples={stats['samples']} "
            f"truncated={stats['truncated_to_cap']}"
        )
        return stats

    # -- session driver --------------------------------------------------------

    def ingest_session(
        self,
        year: int,
        round_num: int,
        session_code: str,
        session: "fastf1.sessions.Session",
        telemetry_policy: Optional[TelemetryPolicy] = None,
    ) -> dict[str, Any]:
        """Ingest one loaded FastF1 session into the canonical store.

        Telemetry is policy-gated and OFF by default: pass an *enabled*
        TelemetryPolicy to opt in (Phase 6C bounded scope).
        """
        resolved = self.resolve_session(year, round_num, session_code)
        if resolved is None:
            return {"attached": False, "stints": 0, "weather": 0, "race_control": 0, "lap_rows": 0}
        session_id, session_type = resolved
        event_ref = f"{year}-R{round_num}-{session_type}"
        season = year
        t0 = datetime.now(timezone.utc)
        n_stints = self.ingest_stints(session.laps, session_id, season, event_ref)
        n_weather = self.ingest_weather(getattr(session, "weather_data", None), session_id, event_ref)
        n_rc = self.ingest_race_control(getattr(session, "race_control_messages", None), session_id, event_ref)
        telemetry: dict[str, Any] = {}
        if telemetry_policy is not None and telemetry_policy.enabled:
            telemetry = self.ingest_telemetry(session, session_id, year, round_num, telemetry_policy)
        with self.store._conn() as conn:
            n_laps = conn.execute(
                "SELECT COUNT(*) FROM canonical_lap_times WHERE session_id = ? AND source_provider = 'fastf1'",
                (session_id,),
            ).fetchone()[0]
        elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
        logger.info(
            f"Canonicalized FastF1 {event_ref}: stints={n_stints} weather={n_weather} "
            f"race_control={n_rc} lap_rows={n_laps} in {elapsed:.1f}s"
        )
        return {
            "attached": True,
            "session_id": session_id,
            "session_type": session_type,
            "stints": n_stints,
            "weather": n_weather,
            "race_control": n_rc,
            "lap_rows": n_laps,
            "telemetry": telemetry,
            "seconds": round(elapsed, 2),
        }
