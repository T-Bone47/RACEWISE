"""Data adapters: provider-specific data normalized to canonical schemas."""

from racewise.data.fastf1_adapter import FastF1Adapter
from racewise.data.api_sports_f1_adapter import APISportsF1Adapter, APISportsF1Error
from racewise.data.f1api_adapter import F1APIAdapter, F1APIError
from racewise.data.f1livepulse_adapter import F1LivePulseAdapter, F1LivePulseError

# Historical ingestion
from racewise.data.historical import (
    F1DBIngester,
    get_f1db_ingester,
    JolpicaIngester,
    get_jolpica_ingester,
    FastF1HistoricalIngester,
    get_fastf1_historical_ingester,
    Normalizer,
    DataQualityChecker,
    Reconciler,
    DiscrepancyType,
    reconcile_sources,
    AvailabilityIndex,
    AvailabilityStatus,
    DataAvailability,
    SessionAvailability,
    SeasonAvailability,
    get_availability_index,
    HistoricalCatalogManager,
    HistoricalCatalog,
    DataSource,
    EntityInventory,
    get_catalog_manager,
    ManifestGenerator,
    generate_dataset_manifest,
    verify_dataset_manifest,
)

__all__ = [
    # Primary adapters
    "FastF1Adapter",
    "APISportsF1Adapter",
    "APISportsF1Error",
    "F1APIAdapter",
    "F1APIError",
    "F1LivePulseAdapter",
    "F1LivePulseError",
    # Historical ingestion
    "F1DBIngester",
    "get_f1db_ingester",
    "JolpicaIngester",
    "get_jolpica_ingester",
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
]