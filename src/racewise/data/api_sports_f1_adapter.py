"""API-Sports Formula 1 adapter: normalizes provider data into canonical domain schemas.

Experimental provider for API-Sports Formula 1 data.
Isolated behind the canonical RACEWISE provider boundary.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
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


class APISportsF1Error(Exception):
    """Raised when API-Sports F1 API returns an error."""
    
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class APISportsF1Adapter:
    """Loads Formula 1 data from API-Sports and normalizes to canonical schemas.
    
    Experimental provider - does not replace FastF1 as primary.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        key_header: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("API_SPORTS_API_KEY", "")
        self.base_url = base_url or os.environ.get("API_SPORTS_F1_BASE_URL", "https://v1.formula-1.api-sports.io")
        self.key_header = key_header or os.environ.get("API_SPORTS_KEY_HEADER", "x-apisports-key")
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                headers={self.key_header: self.api_key},
                timeout=30.0,
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "APISportsF1Adapter":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def _request(self, endpoint: str, params: Optional[dict] = None) -> dict[str, Any]:
        """Make a request to the API-Sports API."""
        client = self._get_client()
        try:
            response = client.get(endpoint, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Check API-Sports response structure
            if "errors" in data and data["errors"]:
                errors = data["errors"]
                if "endpoint" in errors and "Formula1" in errors.get("endpoint", ""):
                    raise APISportsF1Error(
                        "Formula 1 endpoint not available with current subscription",
                        response.status_code,
                    )
                raise APISportsF1Error(f"API-Sports error: {errors}", response.status_code)
            
            return data
        except httpx.HTTPStatusError as e:
            raise APISportsF1Error(f"HTTP {e.response.status_code}: {e.response.text}", e.response.status_code) from e
        except httpx.RequestError as e:
            raise APISportsF1Error(f"Request failed: {e}") from e

    def _check_endpoint_available(self) -> None:
        """Check if Formula 1 endpoint is available, raise if not."""
        health = self.health_check()
        if not health.get("endpoint_available", False):
            raise APISportsF1Error(
                f"Formula 1 endpoint unavailable: {health.get('error', 'Unknown error')}",
            )

    # --- Discovery / Catalog ---

    def get_seasons(self) -> list[int]:
        """Get available Formula 1 seasons."""
        self._check_endpoint_available()
        data = self._request("/formula1/seasons")
        return data.get("response", [])

    def get_races(self, season: int) -> list[dict[str, Any]]:
        """Get all races for a season."""
        self._check_endpoint_available()
        data = self._request("/formula1/races", {"season": season})
        return data.get("response", [])

    def get_race_by_name(self, season: int, race_name: str) -> Optional[dict[str, Any]]:
        """Find a specific race by name within a season."""
        races = self.get_races(season)
        for race in races:
            if race.get("race", {}).get("name", "").lower() == race_name.lower():
                return race
        return None

    # --- Session / Race Data ---

    def get_race_info(self, race_id: int) -> Optional[dict[str, Any]]:
        """Get detailed race information."""
        self._check_endpoint_available()
        data = self._request("/formula1/races", {"id": race_id})
        races = data.get("response", [])
        return races[0] if races else None

    def get_race_results(self, race_id: int) -> list[dict[str, Any]]:
        """Get race results (classification)."""
        self._check_endpoint_available()
        data = self._request("/formula1/results", {"race": race_id})
        return data.get("response", [])

    def get_laps(self, race_id: int) -> list[dict[str, Any]]:
        """Get lap times for a race."""
        self._check_endpoint_available()
        data = self._request("/formula1/laps", {"race": race_id})
        return data.get("response", [])

    def get_pit_stops(self, race_id: int) -> list[dict[str, Any]]:
        """Get pit stops for a race."""
        self._check_endpoint_available()
        data = self._request("/formula1/pitstops", {"race": race_id})
        return data.get("response", [])

    def get_weather(self, race_id: int) -> list[dict[str, Any]]:
        """Get weather data for a race."""
        self._check_endpoint_available()
        data = self._request("/formula1/weather", {"race": race_id})
        return data.get("response", [])

    # --- Normalization to Canonical Schemas ---

    def _normalize_race_info(self, race_data: dict[str, Any]) -> SessionSummary:
        """Normalize race info to SessionSummary."""
        race = race_data.get("race", {})
        circuit = race_data.get("circuit", {})
        
        return SessionSummary(
            session_key=str(race.get("id", "")),
            event_name=race.get("name", ""),
            session_type="Race",
            date=None,  # API-Sports may not provide exact datetime
            circuit=circuit.get("name", ""),
            total_laps=race.get("laps"),
            drivers=[],  # Will be populated from results
        )

    def _normalize_results(self, results: list[dict[str, Any]]) -> list[str]:
        """Extract driver codes from race results."""
        drivers = []
        for result in results:
            driver = result.get("driver", {})
            code = driver.get("code")
            if code:
                drivers.append(code)
        return sorted(drivers)

    def _normalize_lap(self, lap_data: dict[str, Any], driver_code: str) -> Lap:
        """Normalize a lap entry to canonical Lap schema."""
        lap_num = lap_data.get("lap_number")
        time_data = lap_data.get("time", {})
        
        # Parse lap time (format: "1:30.123" or "90.123")
        lap_time_s = None
        time_str = time_data.get("value")
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

        return Lap(
            session_key="",
            driver=driver_code,
            lap_number=lap_num,
            lap_time_s=lap_time_s,
            sector_1_s=None,  # API-Sports may not provide sector times
            sector_2_s=None,
            sector_3_s=None,
            compound=None,  # May not be available
            tyre_life=None,
            stint=None,
            is_pit_in_lap=False,
            is_pit_out_lap=False,
            track_status=None,
            position=lap_data.get("position"),
            is_accurate=None,
            deleted=False,
        )

    def _normalize_pit_stop(self, pit_data: dict[str, Any], driver_code: str) -> PitStop:
        """Normalize a pit stop to canonical PitStop schema."""
        return PitStop(
            session_key="",
            driver=driver_code,
            pit_in_lap=pit_data.get("lap"),
            pit_out_lap=None,
            compound_before=None,
            compound_after=None,
        )

    def _normalize_weather(self, weather_data: dict[str, Any]) -> WeatherRecord:
        """Normalize weather data to canonical WeatherRecord schema."""
        return WeatherRecord(
            session_key="",
            air_temp_c=weather_data.get("air_temperature"),
            track_temp_c=weather_data.get("track_temperature"),
            humidity=weather_data.get("humidity"),
            rainfall=weather_data.get("rainfall", False),
        )

    def get_session_summary(self, race_id: int) -> SessionSummary:
        """Load and normalize full session summary."""
        race_info = self.get_race_info(race_id)
        if not race_info:
            raise ValueError(f"Race {race_id} not found")
        
        summary = self._normalize_race_info(race_info)
        
        # Get results to populate drivers
        results = self.get_race_results(race_id)
        summary.drivers = self._normalize_results(results)
        
        return summary

    def get_laps(self, race_id: int) -> list[Lap]:
        """Load and normalize all laps for a race."""
        laps_data = self.get_laps(race_id)
        results = self.get_race_results(race_id)
        
        # Build driver code lookup from results
        driver_lookup = {}
        for result in results:
            driver = result.get("driver", {})
            driver_num = result.get("number")
            code = driver.get("code")
            if code and driver_num:
                driver_lookup[str(driver_num)] = code
        
        laps = []
        for lap_group in laps_data:
            driver_num = str(lap_group.get("driver", {}).get("number", ""))
            driver_code = driver_lookup.get(driver_num, driver_num)
            
            for lap in lap_group.get("laps", []):
                laps.append(self._normalize_lap(lap, driver_code))
        
        return sorted(laps, key=lambda l: (l.driver, l.lap_number))

    def get_pit_stops_normalized(self, race_id: int) -> list[PitStop]:
        """Load and normalize all pit stops for a race."""
        pit_data = self.get_pit_stops(race_id)
        results = self.get_race_results(race_id)
        
        driver_lookup = {}
        for result in results:
            driver = result.get("driver", {})
            driver_num = result.get("number")
            code = driver.get("code")
            if code and driver_num:
                driver_lookup[str(driver_num)] = code
        
        stops = []
        for stop_group in pit_data:
            driver_num = str(stop_group.get("driver", {}).get("number", ""))
            driver_code = driver_lookup.get(driver_num, driver_num)
            
            for stop in stop_group.get("pitstops", []):
                stops.append(self._normalize_pit_stop(stop, driver_code))
        
        return stops

    def get_weather_normalized(self, race_id: int) -> list[WeatherRecord]:
        """Load and normalize weather data for a race."""
        weather_data = self.get_weather(race_id)
        return [self._normalize_weather(w) for w in weather_data]

    def health_check(self) -> dict[str, Any]:
        """Check API connectivity and authentication."""
        try:
            data = self._request("/formula1/seasons")
            # Check if F1 endpoint exists
            errors = data.get("errors", {})
            if "endpoint" in errors:
                return {
                    "status": "endpoint_unavailable",
                    "authenticated": True,
                    "error": f"Formula 1 endpoint not available: {errors['endpoint']}",
                    "endpoint_available": False,
                }
            return {
                "status": "connected",
                "authenticated": True,
                "seasons_available": len(data.get("response", [])),
                "endpoint_available": True,
            }
        except APISportsF1Error as e:
            if e.status_code == 401:
                return {
                    "status": "error",
                    "authenticated": False,
                    "error": str(e),
                    "endpoint_available": False,
                }
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
def get_apisports_f1_adapter() -> APISportsF1Adapter:
    """Get cached API-Sports F1 adapter instance."""
    return APISportsF1Adapter()