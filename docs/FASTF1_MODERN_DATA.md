# FastF1 Modern Data — Verified Implementation

Phase 6A. Source: FastF1 **3.8.3** (library version recorded as `source_version` on every row). All column mappings below were inspected from the actual dataframes, not assumed.

## What FastF1 provides (verified against dataframes)

- `session.laps` columns: `Time, Driver, DriverNumber, LapTime, LapNumber, Stint, PitOutTime, PitInTime, Sector1Time, Sector2Time, Sector3Time, Sector1SessionTime, Sector2SessionTime, Sector3SessionTime, SpeedI1, SpeedI2, SpeedFL, SpeedST, IsPersonalBest, Compound, TyreLife, FreshTyre, Team, LapStartTime, LapStartDate, TrackStatus, Position, Deleted, DeletedReason, FastF1Generated, IsAccurate`
- `session.weather_data` columns: `Time, AirTemp, Humidity, Pressure, Rainfall, TrackTemp, WindDirection, WindSpeed` (~1 observation/minute; `Time` is a session-relative timedelta)
- `session.race_control_messages` columns: `Time, Category, Message, Status, Flag, Scope, Sector, RacingNumber, Lap`
- Compound vocabulary observed: `SOFT, MEDIUM, HARD` (+ historical: INTERMEDIATE, WET, HYPERSOFT, etc.)
- Track status codes observed in `TrackStatus`: `1, 12, 126, 21, 2671, 671` (bitfield-style, preserved verbatim)

## What is ingested (src/racewise/data/historical/fastf1_canonical.py)

| FastF1 data | Canonical target | Key fields mapped |
|---|---|---|
| laps grouped by (Driver, Stint) | `canonical_stints` | stint_number, compound, lap_start/end (computed from actual lap rows), lap_count, driver (season-scoped resolution) |
| per-lap rows | `canonical_lap_times` (provider=`fastf1`) | lap_number, position, time_s, sector1/2/3_s, compound, tyre_life, stint, is_pit_in/out, track_status, is_accurate, deleted |
| `session.weather_data` | `canonical_weather` | air_temp_c, track_temp_c, humidity, rainfall (bool), wind_direction, wind_speed, pressure, timestamp (ISO-8601), elapsed_s |
| `session.race_control_messages` | `canonical_race_control` | timestamp (ISO datetime), category, message (verbatim), lap |

Identity: `stint_id = sha1("fastf1:stint:<session_id>:<code>:<stint_number>")`, `weather_id/rc_id = sha1(provider:kind:session:index)`, lap rows `sha1("fastf1:lap:<session_id>:<code>:<lap_number>")`. All upserts (`ON CONFLICT DO UPDATE`) → re-running ingestion is idempotent (verified: identical counts on second run).

## Fields deliberately NOT ingested

- `FreshTyre` (boolean) — no canonical column exists yet; documented rather than invented.
- `SpeedI1/I2/FL/ST` — trap speeds are telemetry-adjacent; deferred with the telemetry decision (below).
- `IsPersonalBest`, `FastF1Generated`, `DeletedReason`, `LapStartDate`, `Sector*SessionTime` — provenance/derivation metadata, not engineering facts.
- `Status/Flag/Scope/Sector/RacingNumber` on race-control rows — the canonical table stores category/message/lap; the source embeds flag detail in the message text, which is preserved verbatim.

## Telemetry decision (explicit deferral)

Per-lap **channel telemetry** (throttle/brake/RPM/DRS/X-Y traces at ~Hz-per-sample) is deliberately **not ingested** in Phase 6A:

1. The canonical model has no telemetry table; adding one is a schema decision that should follow actual query needs, not provider shape.
2. Volume: full car-per-lap telemetry for one race is on the order of 10⁶–10⁷ samples (100–1000× the entire current canonical DB). Unbounded ingestion would create a multi-gigabyte store with no consumer yet.
3. The existing tool layer answers pace/strategy/degradation questions from lap-level aggregates; nothing currently queries channel traces.

**Policy when telemetry is needed:** a bounded `(session_id, driver_id, lap_number, signal, distance, value)` long-format table, ingested per-session behind a `--telemetry` flag with measured size, defaulting OFF. Deferred, not forgotten.

## Data volume (measured)

Six ingested sessions add ~13,100 canonical rows (stints + weather + race control + fastf1 lap rows); DB grew 49.6 → 51.5 MB. Projected: a full modern season (24 races × 2 sessions) adds roughly 1–2 M lap rows ≈ 100–200 MB. Well bounded.

## Driver identity

FastF1 3-letter codes are ambiguous across history (e.g. `SCH` maps to 15 canonical drivers). Resolution is **season-scoped**: candidates are narrowed by actual canonical participation in that season; unresolved ambiguity skips rows (no guessing). Verified: 2023 R1–R3 driver sets resolve exactly to the F1DB classification sets.
