"""FastF1 historical ingestion: bulk ingestion of historical FastF1 data.

Provides checkpointed, resumable ingestion of historical FastF1 data across
seasons and sessions.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from racewise.data._lazy import LazyModule

# Deferred imports - see racewise.data._lazy. Importing fastf1 + pandas costs
# ~1.7s warm and ~9s cold; this module only needs them when actually reading
# a session, so the cost is paid on use rather than on import.
fastf1 = LazyModule("fastf1")
pd = LazyModule("pandas")

from racewise.data.fastf1_adapter import FastF1Adapter, enable_cache
from racewise.domain.schemas import (
    Lap,
    PitStop,
    Stint,
    WeatherRecord,
    RaceControlEvent,
    SessionSummary,
)

logger = logging.getLogger(__name__)


@dataclass
class IngestionState:
    """Tracks ingestion progress for resumability."""
    provider: str
    season: int
    event: str
    session_type: str
    status: str  # pending, completed, failed
    started_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None
    records_ingested: int = 0


class FastF1HistoricalIngester:
    """Bulk ingestion of historical FastF1 data with checkpointing."""

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        state_dir: Optional[str] = None,
    ) -> None:
        self.adapter = FastF1Adapter(cache_dir)
        self.state_dir = Path(state_dir) if state_dir else Path.cwd() / "data" / "ingestion_state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "fastf1_ingestion_state.json"
        self.state = self._load_state()

    def _load_state(self) -> dict:
        if self.state_file.exists():
            with open(self.state_file, "r") as f:
                return json.load(f)
        return {"sessions": {}, "last_updated": datetime.utcnow().isoformat()}

    def _save_state(self) -> None:
        self.state["last_updated"] = datetime.utcnow().isoformat()
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def get_season_schedule(self, year: int) -> list[dict]:
        """Get the race calendar for a season."""
        schedule = fastf1.get_event_schedule(year, include_testing=False)
        return schedule[["RoundNumber", "EventName", "EventDate", "EventFormat"]].to_dict("records")

    def get_available_sessions(self, year: int, event: str) -> list[str]:
        """Get available session types for an event."""
        try:
            event_obj = fastf1.get_event(2023, event)  # Use any year to get event info
            return [s for s in ["FP1", "FP2", "FP3", "Q", "SQ", "S", "R"] if hasattr(fastf1.get_session(2023, event, s), "name")]
        except Exception:
            return ["FP1", "FP2", "FP3", "Q", "R"]

    def ingest_season(
        self,
        year: int,
        session_types: Optional[list[str]] = None,
        events: Optional[list[str]] = None,
        resume: bool = True,
        force: bool = False,
    ) -> dict:
        """Ingest all sessions for a season."""
        if session_types is None:
            session_types = ["R", "Q", "FP1", "FP2", "FP3", "S"]

        schedule = self.get_season_schedule(year)
        target_events = events or [row["EventName"] for _, row in pd.DataFrame(schedule).iterrows()]

        results = {
            "season": year,
            "total_events": len(target_events),
            "sessions_ingested": 0,
            "sessions_failed": 0,
            "errors": [],
        }

        for event_row in pd.DataFrame(schedule).iterrows():
            event_name = event_row[1]["EventName"]
            if events and event_name not in target_events:
                continue

            for session_type in session_types:
                state_key = f"{year}-{event_row[1]['EventName'].replace(' ', '_')}-{session_type}"

                if resume and state_key in self.state.get("sessions", {}):
                    if self.state["sessions"][state_key]["status"] == "completed" and not force:
                        logger.info(f"Skipping completed: {state_key}")
                        continue

                self._ingest_session(year, event_row[1]["EventName"], session_type, results)
                self._save_state()

        return results

    def _ingest_session(
        self,
        year: int,
        event: str,
        session_type: str,
        results: dict,
    ) -> None:
        state_key = f"{year}-{event.replace(' ', '_')}-{session_type}"
        self.state.setdefault("sessions", {})[state_key] = {
            "provider": "fastf1",
            "season": year,
            "event": event,
            "session_type": session_type,
            "status": "pending",
            "started_at": datetime.utcnow().isoformat(),
        }
        self._save_state()

        try:
            logger.info(f"Ingesting {year} {event} {session_type}")
            session = self.adapter.load_session(year, event, session_type)

            # Extract all data
            laps = self.adapter.laps(session)
            summary = self.adapter.session_summary(session)
            stints = self.adapter.stints(laps)
            pit_stops = self.adapter.pit_stops(laps)
            weather = self.adapter.weather(fastf1.get_session(2023, event, "R"))  # Need to load properly
            race_control = self.adapter.race_control(fastf1.get_session(2023, event, "R"))

            # Store canonical data
            self._store_session_data(year, event, session_type, {
                "summary": summary,
                "laps": laps,
                "stints": stints,
                "pit_stops": pit_stops,
                "weather": weather,
                "race_control": race_control,
            })

            self.state["sessions"][state_key].update({
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "records_ingested": len(laps),
            })
            logger.info(f"Completed {event} {session_type}: {len(laps)} laps")

        except Exception as e:
            self.state["sessions"][state_key].update({
                "status": "failed",
                "completed_at": datetime.utcnow().isoformat(),
                "error": str(e),
            })
            logger.error(f"Failed {year} {event} {session_type}: {e}")
            raise

    def _store_session_data(
        self,
        year: int,
        event: str,
        session_type: str,
        data: dict,
    ) -> None:
        """Store canonical session data to canonical store."""
        # This would write to the canonical store (Parquet/DB)
        # For now, we'll log the counts
        logger.info(f"  Laps: {len(data.get('laps', []))}")
        logger.info(f"  Stints: {len(data.get('stints', []))}")
        logger.info(f"  Pit stops: {len(data.get('pit_stops', []))}")
        logger.info(f"  Weather records: {len(data.get('weather', []))}")
        logger.info(f"  Race control events: {len(data.get('race_control', []))}")

    def ingest_range(
        self,
        start_year: int,
        end_year: int,
        session_types: Optional[list[str]] = None,
        resume: bool = True,
    ) -> dict:
        """Ingest a range of seasons."""
        overall_results = {
            "start_year": start_year,
            "end_year": end_year,
            "seasons": {},
            "total_sessions": 0,
            "total_errors": 0,
        }

        for year in range(start_year, end_year + 1):
            logger.info(f"=== Ingesting {year} season ===")
            try:
                results = self.ingest_season(year, resume=resume)
                overall_results["seasons"][year] = results
                overall_results["total_sessions"] += results["sessions_ingested"]
                overall_results["total_errors"] += results["sessions_failed"]
            except Exception as e:
                logger.error(f"Failed to ingest {year}: {e}")
                overall_results["seasons"][year] = {"error": str(e)}
                overall_results["total_errors"] += 1

        return overall_results


@lru_cache(maxsize=4)
def get_fastf1_historical_ingester(
    cache_dir: Optional[str] = None,
    state_dir: Optional[str] = None,
) -> FastF1HistoricalIngester:
    return FastF1HistoricalIngester(cache_dir, state_dir)