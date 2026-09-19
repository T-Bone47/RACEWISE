"""Historical Catalog: central registry of all available historical data."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class DataSource:
    """Metadata about a data source."""
    provider: str
    provider_version: str
    source_url: str
    license: str
    attribution: str
    retrieved_at: str
    checksum: Optional[str] = None
    schema_version: str = "1.0"
    coverage_start: Optional[int] = None
    coverage_end: Optional[int] = None
    entities_covered: list[str] = field(default_factory=list)
    known_limitations: list[str] = field(default_factory=list)


@dataclass
class EntityInventory:
    """Inventory of a canonical entity type."""
    entity_type: str
    total_records: int = 0
    seasons_covered: list[int] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)
    earliest_season: Optional[int] = None
    latest_season: Optional[int] = None
    completeness_percentage: float = 0.0
    known_gaps: list[str] = field(default_factory=list)


@dataclass
class HistoricalCatalog:
    """Central catalog of all historical data in RACEWISE."""
    schema_version: str = "1.0"
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    providers: list[DataSource] = field(default_factory=list)
    entities: dict[str, EntityInventory] = field(default_factory=dict)
    seasons_covered: list[int] = field(default_factory=list)
    min_season: Optional[int] = None
    max_season: Optional[int] = None
    total_records: int = 0
    storage_size_bytes: int = 0
    manifest_hash: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "providers": [asdict(p) for p in self.providers],
            "entities": {k: asdict(v) for k, v in self.entities.items()},
            "seasons_covered": self.seasons_covered,
            "min_season": self.min_season,
            "max_season": self.max_season,
            "total_records": self.total_records,
            "storage_size_bytes": self.storage_size_bytes,
            "manifest_hash": self.manifest_hash,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HistoricalCatalog":
        catalog = cls(
            schema_version=data.get("schema_version", "1.0"),
            generated_at=data.get("generated_at", datetime.utcnow().isoformat()),
            providers=[DataSource(**p) for p in data.get("providers", [])],
            entities={k: EntityInventory(**v) for k, v in data.get("entities", {}).items()},
            seasons_covered=data.get("seasons_covered", []),
            min_season=data.get("min_season"),
            max_season=data.get("max_season"),
            total_records=data.get("total_records", 0),
            storage_size_bytes=data.get("storage_size_bytes", 0),
            manifest_hash=data.get("manifest_hash"),
        )
        return catalog


class HistoricalCatalogManager:
    """Manages the historical data catalog."""

    def __init__(self, data_dir: Optional[str] = None) -> None:
        if data_dir is None:
            data_dir = os.environ.get("RACEWISE_DATA_DIR", str(Path.cwd() / "data"))
        self.data_dir = Path(data_dir)
        self.catalog_file = self.data_dir / "manifests" / "historical_catalog.json"
        self.catalog_file.parent.mkdir(parents=True, exist_ok=True)
        self.catalog: Optional["HistoricalCatalog"] = None

    def load(self) -> "HistoricalCatalog":
        """Load catalog from disk."""
        if self.catalog_file.exists():
            with open(self.catalog_file, "r") as f:
                data = json.load(f)
                self.catalog = HistoricalCatalog.from_dict(data)
        else:
            self.catalog = HistoricalCatalog()
        return self.catalog

    def save(self) -> None:
        """Save catalog to disk."""
        if self.catalog:
            self.catalog.generated_at = datetime.utcnow().isoformat()
            with open(self.catalog_file, "w") as f:
                json.dump(self.catalog.to_dict(), f, indent=2)

    def register_provider(self, source: Any) -> None:
        """Register a data source."""
        if self.catalog is None:
            self.catalog = HistoricalCatalog()
        self.catalog.providers.append(source)
        self.save()

    def update_entity_inventory(self, entity_type: str, inventory: Any) -> None:
        """Update entity inventory."""
        if self.catalog is None:
            self.catalog = HistoricalCatalog()
        self.catalog.entities[entity_type] = inventory
        self.save()

    def update_seasons_covered(self, seasons: list[int]) -> None:
        if self.catalog is None:
            self.catalog = HistoricalCatalog()
        self.catalog.seasons_covered = sorted(set(seasons))
        if self.catalog.seasons_covered:
            self.catalog.min_season = min(self.catalog.seasons_covered)
            self.catalog.max_season = max(self.catalog.seasons_covered)
        self.save()

    def get_catalog(self) -> "HistoricalCatalog":
        if self.catalog is None:
            self.load()
        return self.catalog

    def generate_report(self) -> str:
        """Generate a human-readable catalog report."""
        if self.catalog is None:
            self.load()

        lines = [
            "=" * 80,
            "RACEWISE HISTORICAL DATA CATALOG",
            "=" * 80,
            f"Generated: {self.catalog.generated_at}",
            f"Schema Version: {self.catalog.schema_version}",
            f"Seasons Covered: {self.catalog.min_season} - {self.catalog.max_season}",
            f"Total Seasons: {len(self.catalog.seasons_covered)}",
            f"Total Records: {self.catalog.total_records:,}",
            f"Storage Size: {self.catalog.storage_size_bytes / (1024**3):.2f} GB",
            "",
            "PROVIDERS",
            "-" * 40,
        ]

        for provider in self.catalog.providers:
            lines.append(f"  {provider.provider} v{provider.provider_version}")
            lines.append(f"    Source: {provider.source_url}")
            lines.append(f"    License: {provider.license}")
            lines.append(f"    Coverage: {provider.coverage_start} - {provider.coverage_end}")
            lines.append(f"    Entities: {', '.join(provider.entities_covered)}")
            if provider.known_limitations:
                lines.append(f"    Limitations: {', '.join(provider.known_limitations)}")
            lines.append("")

        lines.append("ENTITIES")
        lines.append("-" * 40)

        for entity_type, inventory in sorted(self.catalog.entities.items()):
            lines.append(f"  {entity_type}:")
            lines.append(f"    Records: {inventory.total_records:,}")
            lines.append(f"    Seasons: {inventory.earliest_season} - {inventory.latest_season}")
            lines.append(f"    Providers: {', '.join(inventory.providers)}")
            lines.append(f"    Completeness: {inventory.completeness_percentage:.1f}%")
            if inventory.known_gaps:
                lines.append(f"    Gaps: {', '.join(inventory.known_gaps)}")
            lines.append("")

        return "\n".join(lines)


@lru_cache(maxsize=4)
def get_catalog_manager(data_dir: Optional[str] = None) -> HistoricalCatalogManager:
    return HistoricalCatalogManager(data_dir)