"""RACEWISE Historical Data Ingestion Package.

Provides ingestion pipelines for historical F1 data from multiple providers:
- F1DB: Primary historical foundation (1950-present)
- Jolpica F1: Secondary historical API (successor to Ergast)
- FastF1: Modern detailed data (2018+)
- OpenF1: Modern live/real-time data (2023+)

All providers normalize to canonical RACEWISE schemas.
"""
from __future__ import annotations

from racewise.data.historical.f1db_canonical import CanonicalStore, F1DBCanonicalizer
from racewise.data.historical.f1db_ingest import F1DBIngester, get_f1db_ingester
from racewise.data.historical.canonical_queries import CanonicalQueries, get_canonical_queries
from racewise.data.historical.jolpica_ingest import JolpicaIngester, get_jolpica_ingester
from racewise.data.historical.fastf1_historical_ingest import FastF1HistoricalIngester, get_fastf1_historical_ingester
from racewise.data.historical.normalizer import Normalizer, DataQualityChecker
from racewise.data.historical.reconciliation import Reconciler, DiscrepancyType, reconcile_sources
from racewise.data.historical.availability import AvailabilityIndex, AvailabilityStatus, DataAvailability, SessionAvailability, SeasonAvailability, get_availability_index
from racewise.data.historical.catalog import HistoricalCatalogManager, HistoricalCatalog, DataSource, EntityInventory, get_catalog_manager
from racewise.data.historical.manifest import ManifestGenerator, generate_dataset_manifest, verify_dataset_manifest

__all__ = [
    # F1DB
    "F1DBIngester",
    "get_f1db_ingester",
    "CanonicalStore",
    "F1DBCanonicalizer",
    "CanonicalQueries",
    "get_canonical_queries",
    # Jolpica
    "JolpicaIngester",
    "get_jolpica_ingester",
    # FastF1 Historical
    "FastF1HistoricalIngester",
    "get_fastf1_historical_ingester",
    # Normalization & Quality
    "Normalizer",
    "DataQualityChecker",
    # Reconciliation
    "Reconciler",
    "DiscrepancyType",
    "reconcile_sources",
    # Availability
    "AvailabilityIndex",
    "AvailabilityStatus",
    "DataAvailability",
    "SessionAvailability",
    "SeasonAvailability",
    "get_availability_index",
    # Catalog
    "HistoricalCatalogManager",
    "HistoricalCatalog",
    "DataSource",
    "EntityInventory",
    "get_catalog_manager",
    # Manifest
    "ManifestGenerator",
    "generate_dataset_manifest",
    "verify_dataset_manifest",
    # CLI
    "cli",
]