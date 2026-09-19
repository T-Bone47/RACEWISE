"""Tests for Jolpica ingestion hardening: backoff, jitter, Retry-After, retries."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

from racewise.data.historical.jolpica_ingest import (
    JolpicaError,
    JolpicaIngester,
    JolpicaRateLimitError,
)


class FakeResponse:
    def __init__(self, status_code: int, headers: dict | None = None, payload: dict | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload or {"MRData": {}}

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def _make_ingester(monkeypatch, responses: list, tmp_path: Path) -> tuple[JolpicaIngester, list[float]]:
    """Build an ingester with a scripted response sequence and recorded sleeps."""
    ing = JolpicaIngester(
        cache_dir=str(tmp_path),
        rate_limit=1000.0,  # no throttle delay in tests
        max_retries=3,
        backoff_base_s=0.5,
        backoff_cap_s=4.0,
        jitter=0.0,
    )
    sleeps: list[float] = []
    monkeypatch.setattr(ing, "_request_once", lambda url, params: responses.pop(0))
    monkeypatch.setattr(ing, "_backoff_sleep", lambda attempt, retry_after=None: sleeps.append(retry_after if retry_after is not None else 0.5 * (2 ** attempt)) or 0.0)
    return ing, sleeps


def test_429_then_429_then_200_succeeds_with_backoff(monkeypatch, tmp_path):
    responses = [
        FakeResponse(429, {"Retry-After": "2"}),
        FakeResponse(429),
        FakeResponse(200, payload={"MRData": {"SeasonTable": {"Seasons": [{"season": "2023"}]}}}),
    ]
    ing, sleeps = _make_ingester(monkeypatch, responses, tmp_path)
    data = ing._request("/seasons.json", use_cache=False)
    assert data["MRData"]["SeasonTable"]["Seasons"] == [{"season": "2023"}]
    # Retry-After honored on first retry, exponential backoff on second
    assert sleeps[0] == 2.0
    assert sleeps[1] == 1.0  # 0.5 * 2^1
    assert len(responses) == 0


def test_persistent_429_raises_rate_limit_error(monkeypatch, tmp_path):
    responses = [FakeResponse(429) for _ in range(4)]
    ing, sleeps = _make_ingester(monkeypatch, responses, tmp_path)
    with pytest.raises(JolpicaRateLimitError):
        ing._request("/seasons.json", use_cache=False)
    # max_retries=3 -> 4 attempts total, 3 backoffs
    assert len(sleeps) == 3


def test_5xx_retries_then_succeeds(monkeypatch, tmp_path):
    responses = [
        FakeResponse(503),
        FakeResponse(500),
        FakeResponse(200, payload={"MRData": {"RaceTable": {"Races": []}}}),
    ]
    ing, sleeps = _make_ingester(monkeypatch, responses, tmp_path)
    data = ing._request("/2023.json", use_cache=False)
    assert data["MRData"]["RaceTable"]["Races"] == []
    assert len(sleeps) == 2


def test_persistent_5xx_raises_error(monkeypatch, tmp_path):
    responses = [FakeResponse(503) for _ in range(4)]
    ing, _ = _make_ingester(monkeypatch, responses, tmp_path)
    with pytest.raises(JolpicaError) as exc:
        ing._request("/2023.json", use_cache=False)
    assert "HTTP 503" in str(exc.value)


def test_timeout_retries_then_raises(monkeypatch, tmp_path):
    ing = JolpicaIngester(cache_dir=str(tmp_path), rate_limit=1000.0, max_retries=2, backoff_base_s=0.1)
    calls = []

    def timeout(url, params):
        calls.append(url)
        raise requests.Timeout("timed out")

    monkeypatch.setattr(ing, "_request_once", timeout)
    monkeypatch.setattr(ing, "_backoff_sleep", lambda *a, **k: 0.0)
    with pytest.raises(JolpicaError) as exc:
        ing._request("/seasons.json", use_cache=False)
    assert "timeout" in str(exc.value)
    assert len(calls) == 3  # initial + 2 retries


def test_success_response_is_cached(monkeypatch, tmp_path):
    responses = [FakeResponse(200, payload={"MRData": {"cached": True}})]
    ing, _ = _make_ingester(monkeypatch, responses, tmp_path)
    first = ing._request("/seasons.json")
    # Second call served from cache without another response
    second = ing._request("/seasons.json")
    assert first == second
    assert first["MRData"]["cached"] is True
    cached_files = list(Path(ing.cache_dir).glob("*.json"))
    assert len(cached_files) == 1


def test_404_returns_empty_structure_without_retry(monkeypatch, tmp_path):
    responses = [FakeResponse(404)]
    ing, sleeps = _make_ingester(monkeypatch, responses, tmp_path)
    data = ing._request("/9999.json", use_cache=False)
    assert data == {"MRData": {"RaceTable": {"Races": []}}}
    assert sleeps == []


def test_backoff_respects_cap_and_retry_after(monkeypatch, tmp_path):
    ing = JolpicaIngester(cache_dir=str(tmp_path), backoff_base_s=1.0, backoff_cap_s=5.0, jitter=0.0)
    monkeypatch.setattr(ing, "_rate_limit", lambda: None)
    real_sleep = []
    monkeypatch.setattr("racewise.data.historical.jolpica_ingest.time.sleep", real_sleep.append)
    # Retry-After larger than cap is clamped
    ing._backoff_sleep(10, retry_after=999)
    assert real_sleep[-1] == 5.0
    # Exponential capped
    ing._backoff_sleep(10)
    assert real_sleep[-1] == 5.0
    ing._backoff_sleep(1)
    assert real_sleep[-1] == 2.0
