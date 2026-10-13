"""F1 API (f1api.dev) adapter: normalizes provider data into canonical domain schemas.

Experimental provider for f1api.dev Formula 1 data.
No API key required.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, Optional

import httpx

from racewise.domain.schemas import (
    Lap,
    PitStop,
    RaceControlEvent,
    SessionSummary,
    Stint,
    WeatherRecord,
)

logger = logging.getLogger(__name__)


class F1APIError(Exception):
    """Raised when F1 API returns an error."""
    
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class F1APIAdapter:
    """Loads Formula 1 data from f1api.dev and normalizes to canonical schemas.
    
    Experimental provider - no API key required.
    Provides basic metadata but limited detailed timing data.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
    ) -> None:
        self.base_url = base_url or os.environ.get("F1API_BASE_URL", "https://f1api.dev")
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=10.0,
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "F1APIAdapter":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def _request(self, endpoint: str, params: Optional[dict] = None) -> dict[str, Any]:
        """Make a request to the F1 API."""
        client = self._get_client()
        try:
            response = client.get(endpoint, params=params)
            response.raise_for_status()
            data = response.json()
            return data
        except httpx.HTTPStatusError as e:
            raise F1APIError(f"HTTP {e.response.status_code}: {e.response.text}", e.response.status_code) from e
        except httpx.RequestError as e:
            raise F1APIError(f"Request failed: {e}") from e

    def _check_endpoint_available(self) -> None:
        """Check if endpoint is available (f1api.dev is always available if HTTP 200)."""
        pass  # f1api.dev doesn't have feature-gated endpoints

    # --- Discovery / Catalog ---

    def get_seasons(self) -> list[dict[str, Any]]:
        """Get available Formula 1 seasons."""
        data = self._request("/api/seasons")
        championships = data.get("championships", [])
        return [{"year": c["year"], "championship_id": c["championshipId"]} for c in championships]

    def get_circuits(self) -> list[dict[str, Any]]:
        """Get all circuits."""
        data = self._request("/api/circuits")
        return data.get("circuits", [])

    def get_teams(self) -> list[dict[str, Any]]:
        """Get all teams."""
        data = self._request("/api/teams")
        return data.get("teams", [])

    def get_drivers(self) -> list[dict[str, Any]]:
        """Get all drivers."""
        data = self._request("/api/drivers")
        return data.get("drivers", [])

    def get_race_info(self, year: int, round_num: int) -> Optional[dict[str, Any]]:
        """Get detailed race information."""
        data = self._request(f"/api/{year}/{round_num}/race")
        races = data.get("races", {})
        if not races:
            return None
        return {
            "id": races.get("raceId"),
            "name": races.get("raceName"),
            "date": races.get("date"),
            "time": races.get("time"),
            "circuit": races.get("circuit"),
            "season": data.get("season"),
            "round": data.get("round"),
            "url": races.get("url"),
        }

    def get_season_schedule(self, year: int) -> list[dict[str, Any]]:
        """Get all races for a season."""
        # Use first race to get season data, then extract schedule
        data = self._request(f"/api/{year}/1/race")
        return data.get("races", {})

    # --- Session / Race Data ---

    def _get_race_data(self, year: int, round_num: int) -> Optional[dict[str, Any]]:
        """Get full race data including embedded results, qualifying, etc."""
        data = self._request(f"/api/{year}/{round_num}/race")
        races = data.get("races", {})
        if not races:
            return None
        return races

    def get_race_results(self, year: int, round_num: int) -> list[dict[str, Any]]:
        """Get race results for a specific race from embedded race data."""
        race_data = self._get_race_data(year, round_num)
        if not race_data:
            return []
        return race_data.get("results", [])

    def get_qualifying_results(self, year: int, round_num: int) -> list[dict[str, Any]]:
        """Get qualifying results for a specific race from embedded race data."""
        race_data = self._get_race_data(year, round_num)
        if not race_data:
            return []
        return race_data.get("qualifying", [])

    def get_lap_data(self, year: int, round_num: int) -> list[dict[str, Any]]:
        """Get lap data for a specific race. Not available in f1api.dev."""
        return []

    def get_pit_stops(self, year: int, round_num: int) -> list[dict[str, Any]]:
        """Get pit stops for a specific race. Not available in f1api.dev."""
        return []

    def get_weather(self, year: int, round_num: int) -> list[dict[str, Any]]:
        """Get weather data for a specific race. Not available in f1api.dev."""
        return []

    def get_starting_grid(self, year: int, round_num: int) -> list[dict[str, Any]]:
        """Get starting grid for a specific race. Not available in f1api.dev."""
        return []

    def get_fastest_laps(self, year: int, round_num: int) -> list[dict[str, Any]]:
        """Get fastest laps for a specific race. Not available in f1api.dev."""
        return []

    def get_race_control(self, year: int, round_num: int) -> list[dict[str, Any]]:
        """Get race control messages for a specific race. Not available in f1api.dev."""
        return []

    def get_track_status(self, year: int, round_num: int) -> list[dict[str, Any]]:
        """Get track status for a specific race. Not available in f1api.dev."""
        return []

    # --- Normalization to Canonical Schemas ---

    def _normalize_race_info(self, race_data: dict[str, Any]) -> SessionSummary:
        """Normalize race info to SessionSummary."""
        race = race_data.get("race", {}) if isinstance(race_data.get("race"), dict) else race_data
        circuit = race_data.get("circuit", {})
        
        return SessionSummary(
            session_key=str(race.get("raceId", "")),
            event_name=race.get("raceName", race.get("name", "")),
            session_type="Race",
            date=race.get("date"),
            circuit=circuit.get("circuitName", circuit.get("name", "")) if isinstance(circuit, dict) else circuit,
            total_laps=race.get("laps", {}).get("total") if isinstance(race.get("laps"), dict) else None,
            drivers=[],  # Will be populated from results
        )

    def _normalize_results(self, results: list[dict[str, Any]]) -> list[str]:
        """Extract driver codes from race results."""
        drivers = []
        for result in results:
            driver = result.get("Driver", result.get("driver", {}))
            code = driver.get("code") or driver.get("abbreviation") or driver.get("shortName")
            if code:
                drivers.append(code)
        return sorted(drivers)

    def get_session_summary(self, year: int, round_num: int) -> SessionSummary:
        """Load and normalize full session summary."""
        race_info = self.get_race_info(year, round_num)
        if not race_info:
            raise ValueError(f"Race {year} round {round_num} not found")
        
        summary = self._normalize_race_info(race_info)
        
        # Get results to populate drivers
        results = self.get_race_results(year, round_num)
        summary.drivers = self._normalize_results(results)
        
        return summary

    def get_laps(self, year: int, round_num: int) -> list[Lap]:
        """Load and normalize all laps for a race."""
        laps_data = self.get_lap_data(year, round_num)
        results = self.get_race_results(year, round_num)
        
        # Build driver code lookup from results
        driver_lookup = {}
        for result in results:
            driver = result.get("Driver", result.get("driver", {}))
            code = driver.get("code") or driver.get("abbreviation") or driver.get("shortName")
            number = str(driver.get("number", driver.get("permanentNumber", "")))
            if code and number:
                driver_lookup[number] = code
        
        laps = []
        for lap_group in laps_data:
            driver_num = str(lap_group.get("number", ""))
            driver_code = driver_lookup.get(driver_num, driver_num)
            
            for lap in lap_group.get("Laps", lap_group.get("laps", [])):
                lap_time_s = None
                time_str = lap.get("Time", {}).get("time") if isinstance(lap.get("Time"), dict) else lap.get("time")
                if time_str:
                    try:
                        if ":" in time_str:
                            parts = time_str.split(":")
                            minutes = int(parts[0])
                            seconds = float(parts[1])
                            lap_time_s = minutes * 60 + seconds
                        else:
                            lap_time_s = float(time_str)
                    except (ValueError, TypeError):
                        pass
                
                laps.append(Lap(
                    session_key="",
                    driver=driver_code,
                    lap_number=lap.get("lap", lap.get("lapNumber")),
                    lap_time_s=lap_time_s,
                    sector_1_s=None,
                    sector_2_s=None,
                    sector_3_s=None,
                    compound=None,
                    tyre_life=None,
                    stint=None,
                    is_pit_in_lap=False,
                    is_pit_out_lap=False,
                    track_status=None,
                    position=lap.get("position"),
                    is_accurate=None,
                    deleted=False,
                ))
        return sorted(laps, key=lambda l: (l.driver, l.lap_number))

    def get_pit_stops_normalized(self, year: int, round_num: int) -> list[PitStop]:
        """Load and normalize all pit stops for a race."""
        pit_data = self.get_pit_stops(year, round_num)
        results = self.get_race_results(year, round_num)
        
        driver_lookup = {}
        for result in results:
            driver = result.get("Driver", result.get("driver", {}))
            code = driver.get("code") or driver.get("abbreviation") or driver.get("shortName")
            number = str(driver.get("number", driver.get("permanentNumber", "")))
            if code and number:
                driver_lookup[number] = code
        
        stops = []
        for stop in pit_data:
            driver_num = str(stop.get("driver", {}).get("number", stop.get("driverNumber", "")))
            driver_code = driver_lookup.get(driver_num, driver_num)
            
            stops.append(PitStop(
                session_key="",
                driver=driver_code,
                pit_in_lap=stop.get("lap"),
                pit_out_lap=None,
                compound_before=None,
                compound_after=None,
            ))
        return stops

    def get_weather_normalized(self, year: int, round_num: int) -> list[WeatherRecord]:
        """Load and normalize weather data for a race."""
        weather_data = self.get_weather(year, round_num)
        return [self._normalize_weather(w) for w in weather_data]

    def _normalize_weather(self, weather_data: dict[str, Any]) -> WeatherRecord:
        """Normalize weather data to canonical WeatherRecord schema."""
        return WeatherRecord(
            session_key="",
            air_temp_c=weather_data.get("airTemp") or weather_data.get("air_temperature"),
            track_temp_c=weather_data.get("trackTemp") or weather_data.get("track_temperature"),
            humidity=weather_data.get("humidity"),
            rainfall=weather_data.get("rainfall", False) or weather_data.get("rain", False),
        )

    def health_check(self) -> dict[str, Any]:
        """Check API connectivity."""
        try:
            data = self._request("/api/seasons")
            return {
                "status": "connected",
                "authenticated": True,
                "seasons_available": len(data.get("championships", [])),
                "endpoint_available": True,
            }
        except F1APIError as e:
            return {
                "status": "error",
                "authenticated": True,
                "error": str(e),
                "endpoint_available": False,
            }
        except Exception as e:
            return {
                "status": "error",
                "authenticated": False,
                "error": str(e),
                "endpoint_available": False,
            }


@lru_cache(maxsize=4)
def get_f1api_adapter() -> F1APIAdapter:
    """Get cached F1 API adapter instance."""
    return F1APIAdapter()