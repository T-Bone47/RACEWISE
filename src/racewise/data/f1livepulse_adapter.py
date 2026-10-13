"""F1 Live Pulse (RapidAPI) adapter: normalizes provider data into canonical domain schemas.

Experimental provider for F1 Live Pulse via RapidAPI.
Provides live timing data - may have different capabilities than historical providers.
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


class F1LivePulseError(Exception):
    """Raised when F1 Live Pulse API returns an error."""
    
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class F1LivePulseAdapter:
    """Loads Formula 1 data from F1 Live Pulse (RapidAPI) and normalizes to canonical schemas.
    
    Experimental provider - may provide live/real-time data.
    """
    
    # Endpoint not available / not working with current key
    ENDPOINT_UNAVAILABLE = True

    def __init__(
        self,
        api_key: Optional[str] = None,
        host: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("F1_LIVE_PULSE_API_KEY", "")
        self.host = host or os.environ.get("F1_LIVE_PULSE_HOST", "f1-live-pulse.p.rapidapi.com")
        self.base_url = base_url or os.environ.get("F1_LIVE_PULSE_BASE_URL", "https://f1-live-pulse.p.rapidapi.com")
        self._client: Optional[httpx.Client] = None
        self._endpoint_available = not self.ENDPOINT_UNAVAILABLE

    def _get_client(self) -> httpx.Client:
        if self._client is None and self._endpoint_available:
            self._client = httpx.Client(
                base_url=self.base_url,
                headers={
                    "x-rapidapi-key": self.api_key,
                    "x-rapidapi-host": self.host,
                },
                timeout=10.0,
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "F1LivePulseAdapter":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def _request(self, endpoint: str, params: Optional[dict] = None) -> dict[str, Any]:
        """Make a request to the F1 Live Pulse API."""
        if not self._endpoint_available:
            raise F1LivePulseError("F1 Live Pulse endpoint not available with current subscription")
        
        client = self._get_client()
        try:
            response = client.get(endpoint, params=params)
            response.raise_for_status()
            data = response.json()
            return data
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self._endpoint_available = False
            raise F1LivePulseError(f"HTTP {e.response.status_code}: {e.response.text}", e.response.status_code) from e
        except httpx.RequestError as e:
            raise F1LivePulseError(f"Request failed: {e}") from e

    def _check_endpoint_available(self) -> bool:
        """Check if endpoint is available by making a lightweight request."""
        if not self._endpoint_available:
            return False
        try:
            self._request("/")
            return True
        except Exception:
            self._endpoint_available = False
            return False

    # --- All methods return empty/unavailable ---

    def get_seasons(self) -> list[dict[str, Any]]:
        return []

    def get_circuits(self) -> list[dict[str, Any]]:
        return []

    def get_teams(self) -> list[dict[str, Any]]:
        return []

    def get_drivers(self) -> list[dict[str, Any]]:
        return []

    def get_race_info(self, year: int, round_num: int) -> Optional[dict[str, Any]]:
        return None

    def get_season_schedule(self, year: int) -> list[dict[str, Any]]:
        return []

    def get_race_results(self, year: int, round_num: int) -> list[dict[str, Any]]:
        return []

    def get_qualifying_results(self, year: int, round_num: int) -> list[dict[str, Any]]:
        return []

    def get_lap_data(self, year: int, round_num: int) -> list[dict[str, Any]]:
        return []

    def get_pit_stops(self, year: int, round_num: int) -> list[dict[str, Any]]:
        return []

    def get_weather(self, year: int, round_num: int) -> list[dict[str, Any]]:
        return []

    def get_starting_grid(self, year: int, round_num: int) -> list[dict[str, Any]]:
        return []

    def get_fastest_laps(self, year: int, round_num: int) -> list[dict[str, Any]]:
        return []

    def get_race_control(self, year: int, round_num: int) -> list[dict[str, Any]]:
        return []

    def get_track_status(self, year: int, round_num: int) -> list[dict[str, Any]]:
        return []

    def get_session_summary(self, year: int, round_num: int) -> SessionSummary:
        return SessionSummary(
            session_key="",
            event_name="",
            session_type="Race",
            date=None,
            circuit=None,
            total_laps=None,
            drivers=[],
        )

    def get_laps(self, year: int, round_num: int) -> list[Lap]:
        return []

    def get_pit_stops_normalized(self, year: int, round_num: int) -> list[PitStop]:
        return []

    def get_weather_normalized(self, year: int, round_num: int) -> list[WeatherRecord]:
        return []

    def health_check(self) -> dict[str, Any]:
        if not self._endpoint_available:
            return {
                "status": "unavailable",
                "authenticated": False,
                "error": "F1 Live Pulse endpoint not available with current RapidAPI subscription",
                "endpoint_available": False,
            }
        try:
            self._request("/")
            return {
                "status": "connected",
                "authenticated": True,
                "endpoint_available": True,
            }
        except Exception as e:
            return {
                "status": "error",
                "authenticated": False,
                "error": str(e),
                "endpoint_available": False,
            }


@lru_cache(maxsize=4)
def get_f1livepulse_adapter() -> "F1LivePulseAdapter":
    """Get cached F1 Live Pulse adapter instance."""
    return F1LivePulseAdapter()