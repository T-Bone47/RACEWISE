"""RACEWISE Historical Data Ingestion Package.

Provides ingestion pipelines for historical F1 data from multiple providers:
- F1DB: Primary historical foundation (1950-present)
- Jolpica F1: Secondary historical API (successor to Ergast)
- FastF1: Modern detailed data (2018+)
- OpenF1: Modern live/real-time data (2023+)

All providers normalize to canonical RACEWISE schemas.

Exports resolve lazily (see :mod:`racewise.lazy_exports`) so that importing one
ingester no longer links every other provider - in particular the FastF1 chain,
which pulls in fastf1 + pandas at module import time.
"""

from __future__ import annotations

from racewise.lazy_exports import install_lazy_exports

_EXPORTS = {
    # F1DB
    "F1DBIngester": "racewise.data.historical.f1db_ingest",
    "get_f1db_ingester": "racewise.data.historical.f1db_ingest",
    "CanonicalStore": "racewise.data.historical.f1db_canonical",
    "F1DBCanonicalizer": "racewise.data.historical.f1db_canonical",
    "CanonicalQueries": "racewise.data.historical.canonical_queries",
    "get_canonical_queries": "racewise.data.historical.canonical_queries",
    # Jolpica
    "JolpicaIngester": "racewise.data.historical.jolpica_ingest",
    "get_jolpica_ingester": "racewise.data.historical.jolpica_ingest",
    # FastF1 historical
    "FastF1HistoricalIngester": "racewise.data.historical.fastf1_historical_ingest",
    "get_fastf1_historical_ingester": "racewise.data.historical.fastf1_historical_ingest",
    # Normalization & quality
    "Normalizer": "racewise.data.historical.normalizer",
    "DataQualityChecker": "racewise.data.historical.normalizer",
    # Reconciliation
    "Reconciler": "racewise.data.historical.reconciliation",
    "DiscrepancyType": "racewise.data.historical.reconciliation",
    "reconcile_sources": "racewise.data.historical.reconciliation",
    # Availability
    "AvailabilityIndex": "racewise.data.historical.availability",
    "AvailabilityStatus": "racewise.data.historical.availability",
    "DataAvailability": "racewise.data.historical.availability",
    "SessionAvailability": "racewise.data.historical.availability",
    "SeasonAvailability": "racewise.data.historical.availability",
    "get_availability_index": "racewise.data.historical.availability",
    # Catalog
    "HistoricalCatalogManager": "racewise.data.historical.catalog",
    "HistoricalCatalog": "racewise.data.historical.catalog",
    "DataSource": "racewise.data.historical.catalog",
    "EntityInventory": "racewise.data.historical.catalog",
    "get_catalog_manager": "racewise.data.historical.catalog",
    # Manifest
    "ManifestGenerator": "racewise.data.historical.manifest",
    "generate_dataset_manifest": "racewise.data.historical.manifest",
    "verify_dataset_manifest": "racewise.data.historical.manifest",
}

install_lazy_exports(globals(), _EXPORTS)