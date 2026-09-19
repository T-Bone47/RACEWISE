"""F1DB ingestion: processes F1DB release data into the canonical store.

F1DB is the primary historical foundation for RACEWISE, providing all-time F1
data from 1950 to present under CC BY 4.0 license.

Source: https://github.com/f1db/f1db
License: CC BY 4.0

The pipeline is idempotent: every canonical id is derived from stable F1DB
source keys, so re-running ingestion for the same release produces identical
logical rows. CSV files are streamed row-by-row into bulk executemany calls;
raw file contents are never held fully in memory twice.
"""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import shutil
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Optional

import requests

from racewise.data.historical.f1db_canonical import CanonicalStore, F1DBCanonicalizer

logger = logging.getLogger(__name__)

F1DB_REPO = "f1db/f1db"
F1DB_API_URL = f"https://api.github.com/repos/{F1DB_REPO}/releases/latest"

# Canonical mapping of logical entity -> F1DB CSV file name.
F1DB_FILES: dict[str, str] = {
    "seasons": "f1db-seasons.csv",
    "races": "f1db-races.csv",
    "circuits": "f1db-circuits.csv",
    "drivers": "f1db-drivers.csv",
    "constructors": "f1db-constructors.csv",
    "race_results": "f1db-races-race-results.csv",
    "sprint_results": "f1db-races-sprint-race-results.csv",
    "qualifying_results": "f1db-races-qualifying-results.csv",
    "sprint_qualifying_results": "f1db-races-sprint-qualifying-results.csv",
    "starting_grid": "f1db-races-starting-grid-positions.csv",
    "pit_stops": "f1db-races-pit-stops.csv",
    "fastest_laps": "f1db-races-fastest-laps.csv",
    "free_practice_1": "f1db-races-free-practice-1-results.csv",
    "free_practice_2": "f1db-races-free-practice-2-results.csv",
    "free_practice_3": "f1db-races-free-practice-3-results.csv",
    "free_practice_4": "f1db-races-free-practice-4-results.csv",
    "warming_up": "f1db-races-warming-up-results.csv",
    "qualifying_1": "f1db-races-qualifying-1-results.csv",
    "qualifying_2": "f1db-races-qualifying-2-results.csv",
    "pre_qualifying": "f1db-races-pre-qualifying-results.csv",
}


@dataclass
class F1DBRelease:
    """F1DB release metadata."""

    tag_name: str
    name: str
    published_at: str
    assets: list[dict]


class F1DBError(Exception):
    """Raised when F1DB operations fail."""


def _iter_csv(extract_dir: Path, filename: str) -> Iterator[dict]:
    """Stream rows from an F1DB CSV file (memory-bounded)."""
    file_path = extract_dir / filename
    if not file_path.exists():
        logger.warning(f"F1DB file not found: {filename}")
        return
    with open(file_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row


class F1DBIngester:
    """Downloads and canonicalizes F1DB release data."""

    def __init__(self, data_dir: Optional[str] = None, db_path: Optional[str] = None) -> None:
        if data_dir is None:
            data_dir = os.environ.get("RACEWISE_DATA_DIR", str(Path.cwd() / "data"))
        self.data_dir = Path(data_dir)
        self.raw_dir = self.data_dir / "raw" / "f1db"
        self.canonical_dir = self.data_dir / "canonical"
        self.manifests_dir = self.data_dir / "manifests"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.canonical_dir.mkdir(parents=True, exist_ok=True)
        self.manifests_dir.mkdir(parents=True, exist_ok=True)
        self.store = CanonicalStore(db_path)

    def fetch_latest_release(self) -> F1DBRelease:
        """Fetch the latest F1DB release metadata from GitHub (or local)."""
        # Prefer any already-extracted local version containing the CSV set.
        for candidate in sorted(self.raw_dir.glob("f1db-*"), reverse=True):
            if candidate.is_dir() and (candidate / "f1db-races.csv").exists():
                version = candidate.name.replace("f1db-", "").lstrip("v")
                logger.info(f"Using existing extracted data at {candidate}")
                return F1DBRelease(
                    tag_name=f"v{version}",
                    name=f"F1DB v{version}",
                    published_at=datetime.now(timezone.utc).isoformat(),
                    assets=[{"name": "f1db-csv.zip", "browser_download_url": ""}],
                )

        response = requests.get(F1DB_API_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        return F1DBRelease(
            tag_name=data["tag_name"],
            name=data["name"],
            published_at=data["published_at"],
            assets=data["assets"],
        )

    def download_release(self, release: F1DBRelease, force: bool = False) -> Path:
        """Download and extract the F1DB release CSV zip."""
        version = release.tag_name.lstrip("v")
        extract_dir = self.raw_dir / f"f1db-{version}"
        if extract_dir.exists() and any(extract_dir.iterdir()):
            logger.info(f"Extract directory already exists: {extract_dir}")
            return extract_dir

        zip_asset = None
        for asset in release.assets:
            if asset["name"].endswith(".zip") and "csv" in asset["name"].lower():
                zip_asset = asset
                break
        if not zip_asset:
            raise F1DBError("No CSV zip asset found in release")

        zip_path = self.raw_dir / zip_asset["name"]
        if not (zip_path.exists() and not force):
            logger.info(f"Downloading F1DB release from {zip_asset['browser_download_url']}")
            response = requests.get(zip_asset["browser_download_url"], timeout=300, stream=True)
            response.raise_for_status()
            with open(zip_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=1 << 16):
                    f.write(chunk)

        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True)
        logger.info(f"Extracting to {extract_dir}")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)
        return extract_dir

    def _file_sha256(self, path: Path) -> str:
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def canonicalize(
        self,
        release: F1DBRelease,
        extract_dir: Path,
        measure: bool = False,
    ) -> dict[str, Any]:
        """Canonicalize the extracted F1DB release into the canonical store.

        Idempotent: safe to run repeatedly for the same release.
        """
        started = time.perf_counter()
        version = release.tag_name.lstrip("v")
        canonicalizer = F1DBCanonicalizer(self.store, source_version=version)

        stats: dict[str, Any] = {}
        t0 = time.perf_counter()
        stats["seasons"] = canonicalizer.ingest_seasons(list(_iter_csv(extract_dir, F1DB_FILES["seasons"])))
        stats["circuits"] = canonicalizer.ingest_circuits(list(_iter_csv(extract_dir, F1DB_FILES["circuits"])))
        stats["drivers"] = canonicalizer.ingest_drivers(list(_iter_csv(extract_dir, F1DB_FILES["drivers"])))
        stats["constructors"] = canonicalizer.ingest_constructors(list(_iter_csv(extract_dir, F1DB_FILES["constructors"])))
        stats["races"] = canonicalizer.ingest_races(list(_iter_csv(extract_dir, F1DB_FILES["races"])))
        stats["_entity_seconds"] = round(time.perf_counter() - t0, 2)

        # Sessions: only where F1DB represents them (scheduled or with detail rows).
        t0 = time.perf_counter()
        races_rows = list(_iter_csv(extract_dir, F1DB_FILES["races"]))
        evidence = canonicalizer.collect_detail_evidence(extract_dir)
        stats["sessions"] = canonicalizer.construct_sessions(races_rows, evidence)
        stats["_session_seconds"] = round(time.perf_counter() - t0, 2)

        # Session-level results.
        t0 = time.perf_counter()
        stats["results"] = canonicalizer.ingest_results(list(_iter_csv(extract_dir, F1DB_FILES["race_results"])), "RACE")
        stats["sprint_results"] = canonicalizer.ingest_results(list(_iter_csv(extract_dir, F1DB_FILES["sprint_results"])), "SPRINT")
        stats["qualifying"] = canonicalizer.ingest_qualifying(list(_iter_csv(extract_dir, F1DB_FILES["qualifying_results"])), "QUALIFYING")
        stats["sprint_qualifying"] = canonicalizer.ingest_qualifying(list(_iter_csv(extract_dir, F1DB_FILES["sprint_qualifying_results"])), "SPRINT_QUALIFYING")
        stats["starting_grid"] = canonicalizer.ingest_starting_grid(list(_iter_csv(extract_dir, F1DB_FILES["starting_grid"])), "RACE")
        stats["pit_stops"] = canonicalizer.ingest_pit_stops(list(_iter_csv(extract_dir, F1DB_FILES["pit_stops"])), "RACE")
        stats["fastest_laps"] = canonicalizer.ingest_fastest_laps(list(_iter_csv(extract_dir, F1DB_FILES["fastest_laps"])), "RACE")
        stats["practice_results"] = sum(
            canonicalizer.ingest_practice_results(
                list(_iter_csv(extract_dir, F1DB_FILES[key])), f"FREE_PRACTICE_{n}"
            )
            for n, key in ((1, "free_practice_1"), (2, "free_practice_2"), (3, "free_practice_3"), (4, "free_practice_4"))
        )
        stats["warming_up_results"] = canonicalizer.ingest_practice_results(
            list(_iter_csv(extract_dir, F1DB_FILES["warming_up"])), "WARMING_UP"
        )
        # Historic multi-session qualifying eras (1980-2005 Q1/Q2, pre-qualifying).
        stats["qualifying_1_2"] = sum(
            canonicalizer.ingest_qualifying(list(_iter_csv(extract_dir, F1DB_FILES[key])), f"QUALIFYING_{n}")
            for n, key in ((1, "qualifying_1"), (2, "qualifying_2"))
        )
        stats["pre_qualifying"] = canonicalizer.ingest_qualifying(
            list(_iter_csv(extract_dir, F1DB_FILES["pre_qualifying"])), "PRE_QUALIFYING"
        )
        stats["_detail_seconds"] = round(time.perf_counter() - t0, 2)

        # Availability catalog: data-derived.
        stats["catalog_entries"] = canonicalizer.rebuild_catalog()

        counts = self.store.counts()
        stats["canonical_counts"] = counts

        elapsed = time.perf_counter() - started
        total_rows = sum(
            counts.get(t, 0)
            for t in (
                "canonical_sessions", "canonical_results", "canonical_qualifying",
                "canonical_pit_stops", "canonical_lap_times", "canonical_stints",
                "canonical_weather", "canonical_race_control",
            )
        )
        stats["runtime_seconds"] = round(elapsed, 2)
        stats["session_rows_per_second"] = int(total_rows / elapsed) if elapsed > 0 else None
        db_size = self.store.db_path.stat().st_size
        stats["db_size_bytes"] = db_size

        # Manifest with per-file hashes for provenance.
        manifest = {
            "provider": "f1db",
            "provider_version": release.tag_name,
            "release_name": release.name,
            "published_at": release.published_at,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "source_url": f"https://github.com/f1db/f1db/releases/tag/{release.tag_name}",
            "schema_version": "1.0",
            "files": {
                name: {
                    "sha256": self._file_sha256(extract_dir / filename),
                    "size_bytes": (extract_dir / filename).stat().st_size,
                }
                for name, filename in F1DB_FILES.items()
                if (extract_dir / filename).exists()
            },
            "ingestion": stats,
        }
        manifest_path = self.manifests_dir / f"f1db_{version}_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        logger.info(f"F1DB canonicalization complete in {elapsed:.1f}s: {stats}")
        return stats

    def rebuild(self) -> None:
        """Delete and recreate the canonical database.

        Safe because every canonical row is derived from raw F1DB CSVs.
        Used when the canonical schema changes (e.g. Phase 5.5B added
        provenance columns and deterministic ids).
        """
        if self.store.db_path.exists():
            logger.info(f"Rebuilding canonical database at {self.store.db_path}")
            self.store.db_path.unlink()
        self.store = CanonicalStore(str(self.store.db_path))

    def ingest_release(self, release: Optional[F1DBRelease] = None, force: bool = False) -> dict:
        """Full ingestion pipeline for an F1DB release."""
        if release is None:
            release = self.fetch_latest_release()
        logger.info(f"Processing F1DB release: {release.tag_name}")
        extract_dir = self.download_release(release, force)
        return self.canonicalize(release, extract_dir)


@lru_cache(maxsize=4)
def get_f1db_ingester(data_dir: Optional[str] = None) -> F1DBIngester:
    return F1DBIngester(data_dir)
