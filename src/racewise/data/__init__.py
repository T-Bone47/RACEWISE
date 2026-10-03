"""Data adapters: provider-specific data normalized to canonical schemas.

Exports are resolved lazily (see :mod:`racewise.lazy_exports`). Previously this
module imported every adapter *and* the entire historical ingestion stack
eagerly, so touching any submodule linked fastf1 + pandas and cost seconds on
every process start. Import behaviour is unchanged; only the timing moved.
"""

from __future__ import annotations

from racewise.lazy_exports import install_lazy_exports

_EXPORTS = {
    # Primary adapters
    "FastF1Adapter": "racewise.data.fastf1_adapter",
    "APISportsF1Adapter": "racewise.data.api_sports_f1_adapter",
    "APISportsF1Error": "racewise.data.api_sports_f1_adapter",
    "F1APIAdapter": "racewise.data.f1api_adapter",
    "F1APIError": "racewise.data.f1api_adapter",
    "F1LivePulseAdapter": "racewise.data.f1livepulse_adapter",
    "F1LivePulseError": "racewise.data.f1livepulse_adapter",
    # Historical ingestion
    "F1DBIngester": "racewise.data.historical.f1db_ingest",
    "get_f1db_ingester": "racewise.data.historical.f1db_ingest",
    "JolpicaIngester": "racewise.data.historical.jolpica_ingest",
    "get_jolpica_ingester": "racewise.data.historical.jolpica_ingest",
    "FastF1HistoricalIngester": "racewise.data.historical.fastf1_historical_ingest",
    "get_fastf1_historical_ingester": "racewise.data.historical.fastf1_historical_ingest",
    "Normalizer": "racewise.data.historical.normalizer",
    "DataQualityChecker": "racewise.data.historical.normalizer",
    "Reconciler": "racewise.data.historical.reconciliation",
    "DiscrepancyType": "racewise.data.historical.reconciliation",
    "reconcile_sources": "racewise.data.historical.reconciliation",
    "AvailabilityIndex": "racewise.data.historical.availability",
    "AvailabilityStatus": "racewise.data.historical.availability",
    "DataAvailability": "racewise.data.historical.availability",
    "SessionAvailability": "racewise.data.historical.availability",
    "SeasonAvailability": "racewise.data.historical.availability",
    "get_availability_index": "racewise.data.historical.availability",
    "HistoricalCatalogManager": "racewise.data.historical.catalog",
    "HistoricalCatalog": "racewise.data.historical.catalog",
    "DataSource": "racewise.data.historical.catalog",
    "EntityInventory": "racewise.data.historical.catalog",
    "get_catalog_manager": "racewise.data.historical.catalog",
    "ManifestGenerator": "racewise.data.historical.manifest",
    "generate_dataset_manifest": "racewise.data.historical.manifest",
    "verify_dataset_manifest": "racewise.data.historical.manifest",
}

install_lazy_exports(globals(), _EXPORTS)