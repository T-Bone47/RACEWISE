"""Jolpica F1 ingestion: API-based historical data from the Jolpica F1 API.

Jolpica F1 is the successor to Ergast, providing historical F1 data via a
RESTful API. It's the successor to the Ergast API.

Source: https://github.com/jolpica/jolpica-f1
API: https://api.jolpi.ca/ergast/f1/
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import requests

from racewise.domain.schemas import (
    SessionSummary,
    Lap,
    PitStop,
    Stint,
    WeatherRecord,
    RaceControlEvent,
)

logger = logging.getLogger(__name__)

JOLPICA_BASE_URL = "https://api.jolpi.ca/ergast/f1"
DEFAULT_USER_AGENT = "RACEWISE/1.0 (+https://github.com/racewise; contact@racewise.dev)"


class JolpicaError(Exception):
    """Raised when Jolpica API operations fail."""
    pass


@dataclass
class JolpicaResponse:
    """Standardized Jolpica API response wrapper."""
    data: list[dict]
    total: int
    limit: int
    offset: int
    raw_response: dict


class JolpicaRateLimitError(JolpicaError):
    """Raised when Jolpica keeps returning 429 after all retries."""


class JolpicaIngester:
    """Ingests historical F1 data from the Jolpica API.

    Politeness guarantees (Phase 5.5B):
    - configurable minimum interval between requests
    - exponential backoff with jitter on 429/5xx and timeouts
    - Retry-After header honored when present
    - bounded retries, then a structured failure (never hammering)
    - disk cache + resumable callers
    """

    RETRYABLE_STATUS = {429, 500, 502, 503, 504}

    def __init__(
        self,
        base_url: str = JOLPICA_BASE_URL,
        user_agent: str = DEFAULT_USER_AGENT,
        cache_dir: Optional[str] = None,
        rate_limit: float = 4.0,  # requests per second
        timeout: float = 30.0,
        max_retries: int = 4,
        backoff_base_s: float = 1.0,
        backoff_cap_s: float = 60.0,
        jitter: float = 0.25,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})
        self.rate_limit = rate_limit
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base_s = backoff_base_s
        self.backoff_cap_s = backoff_cap_s
        self.jitter = jitter
        self._last_request_time = 0.0

        if cache_dir is None:
            cache_dir = os.environ.get("RACEWISE_DATA_DIR", str(Path.cwd() / "data"))
        self.cache_dir = Path(cache_dir) / "raw" / "jolpica"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        min_interval = 1.0 / self.rate_limit
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)

    def _backoff_sleep(self, attempt: int, retry_after: Optional[float] = None) -> float:
        """Compute and sleep one backoff interval. Returns the slept seconds."""
        if retry_after is not None:
            delay = min(float(retry_after), self.backoff_cap_s)
        else:
            exp = self.backoff_base_s * (2 ** attempt)
            delay = min(exp, self.backoff_cap_s)
            if self.jitter > 0:
                delay *= 1.0 + random.uniform(-self.jitter, self.jitter)
        delay = max(delay, 0.0)
        if delay > 0:
            time.sleep(delay)
        return delay

    def _request_once(self, url: str, params: Optional[dict]) -> requests.Response:
        self._rate_limit()
        self._last_request_time = time.time()
        return self.session.get(url, params=params, timeout=self.timeout)

    def _request(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        use_cache: bool = True,
    ) -> dict:
        """Request with cache, rate limiting, and bounded exponential backoff."""
        url = f"{self.base_url}{endpoint}"
        cache_key = hashlib.md5(f"{url}?{str(sorted(params.items()) if params else '')}".encode()).hexdigest()
        cache_path = self.cache_dir / f"{cache_key}.json"

        if use_cache and cache_path.exists():
            with open(cache_path, "r") as f:
                logger.debug(f"Cache hit: {endpoint}")
                return json.load(f)

        last_error: Optional[str] = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._request_once(url, params)
            except requests.Timeout as exc:
                last_error = f"timeout: {exc}"
                if attempt < self.max_retries:
                    self._backoff_sleep(attempt)
                    continue
                raise JolpicaError(f"Jolpica request failed after {self.max_retries} retries ({last_error})") from exc
            except requests.ConnectionError as exc:
                last_error = f"connection error: {exc}"
                if attempt < self.max_retries:
                    self._backoff_sleep(attempt)
                    continue
                raise JolpicaError(f"Jolpica request failed after {self.max_retries} retries ({last_error})") from exc

            if response.status_code == 404:
                return {"MRData": {"RaceTable": {"Races": []}}}

            if response.status_code in self.RETRYABLE_STATUS:
                last_error = f"HTTP {response.status_code}"
                if attempt < self.max_retries:
                    retry_after = response.headers.get("Retry-After")
                    retry_after_s: Optional[float]
                    try:
                        retry_after_s = float(retry_after) if retry_after is not None else None
                    except (TypeError, ValueError):
                        retry_after_s = None
                    self._backoff_sleep(attempt, retry_after_s)
                    continue
                if response.status_code == 429:
                    raise JolpicaRateLimitError(
                        f"Jolpica rate limit persisted after {self.max_retries} retries: {last_error}"
                    )
                raise JolpicaError(f"Jolpica request failed after {self.max_retries} retries ({last_error})")

            response.raise_for_status()
            data = response.json()
            if use_cache:
                with open(cache_path, "w") as f:
                    json.dump(data, f)
            return data

        raise JolpicaError(f"Jolpica request failed ({last_error})")  # pragma: no cover

    def _paginate(self, endpoint: str, params: Optional[dict] = None) -> list[dict]:
        """Fetch all pages of a paginated endpoint."""
        if params is None:
            params = {}
        params.setdefault("limit", 1000)
        params.setdefault("offset", 0)

        all_items = []
        while True:
            data = self._request(endpoint, params)
            items = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
            if not items:
                break
            all_items.extend(items)
            if len(items) < params["limit"]:
                break
            params["offset"] += params["limit"]
        return all_items

    # --- Discovery / Catalog ---

    def get_seasons(self) -> list[dict]:
        """Get all available seasons."""
        data = self._request("/seasons.json")
        return data.get("MRData", {}).get("SeasonTable", {}).get("Seasons", [])

    def get_races(self, season: int) -> list[dict]:
        """Get all races for a season."""
        return self._paginate(f"/{season}.json")

    def get_circuits(self, season: Optional[int] = None) -> list[dict]:
        """Get circuits, optionally for a specific season."""
        if season:
            return self._paginate(f"/{season}/circuits.json")
        return self._paginate("/circuits.json")

    def get_drivers(self, season: Optional[int] = None) -> list[dict]:
        if season:
            return self._paginate(f"/{season}/drivers.json")
        return self._paginate("/drivers.json")

    def get_constructors(self, season: Optional[int] = None) -> list[dict]:
        if season:
            return self._paginate(f"/{season}/constructors.json")
        return self._paginate("/constructors.json")

    # --- Session / Race Data ---

    def get_race_results(self, season: int, round_num: int) -> list[dict]:
        """Get race results for a specific race."""
        data = self._request(f"/{season}/{round_num}/results.json")
        return data.get("MRData", {}).get("RaceTable", {}).get("Races", [])

    def get_qualifying_results(self, season: int, round_num: int) -> list[dict]:
        data = self._request(f"/{season}/{round_num}/qualifying.json")
        return data.get("MRData", {}).get("RaceTable", {}).get("Races", [])

    def get_lap_data(self, season: int, round_num: int) -> list[dict]:
        """Get lap times for a specific race."""
        # Jolpica lap data is paginated per driver
        data = self._request(f"/{season}/{round_num}/laps.json", {"limit": 2000})
        return data.get("MRData", {}).get("RaceTable", {}).get("Races", [])

    def get_pit_stops(self, season: int, round_num: int) -> list[dict]:
        """Get pit stops for a specific race."""
        data = self._request(f"/{season}/{round_num}/pitstops.json")
        return data.get("MRData", {}).get("RaceTable", {}).get("Races", [])

    def get_driver_standings(self, season: int) -> list[dict]:
        data = self._request(f"/{season}/driverStandings.json")
        return data.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])

    def get_constructor_standings(self, season: int) -> list[dict]:
        data = self._request(f"/{season}/constructorStandings.json")
        return data.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])

    def get_fastest_laps(self, season: int, round_num: int) -> list[dict]:
        data = self._request(f"/{season}/{round_num}/fastest/1/results.json")
        return data.get("MRData", {}).get("RaceTable", {}).get("Races", [])

    def get_race_schedule(self, season: int) -> list[dict]:
        """Get the full race schedule for a season."""
        data = self._request(f"/{season}.json")
        return data.get("MRData", {}).get("RaceTable", {}).get("Races", [])

    def get_race_info(self, season: int, round_num: int) -> Optional[dict]:
        """Get detailed race information."""
        data = self._request(f"/{season}/{round_num}.json")
        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        return races[0] if races else None

    def health_check(self) -> dict[str, Any]:
        """Check API connectivity."""
        try:
            data = self._request("/seasons.json", use_cache=False)
            seasons = data.get("MRData", {}).get("SeasonTable", {}).get("Seasons", [])
            return {
                "status": "connected",
                "seasons_available": len(seasons),
                "endpoint_available": True,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "endpoint_available": False,
            }


@lru_cache(maxsize=4)
def get_jolpica_ingester(
    base_url: str = JOLPICA_BASE_URL,
    user_agent: str = DEFAULT_USER_AGENT,
    cache_dir: Optional[str] = None,
) -> JolpicaIngester:
    rate_limit = float(os.environ.get("JOLPICA_RATE_LIMIT", "4.0"))
    return JolpicaIngester(base_url, user_agent, cache_dir, rate_limit=rate_limit)