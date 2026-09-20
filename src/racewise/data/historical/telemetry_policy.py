"""Telemetry capability and policy interfaces (Phase 6B).

Phase 6B does NOT ingest or store channel telemetry. These interfaces
formalize the deferral so Phase 6C can activate a bounded consumer
without schema churn:

- TelemetrySessionStatus: per-session state machine (UNAVAILABLE until a
  consumer exists and ingestion has run).
- TelemetryPolicy: configuration object; `enabled` defaults to False and
  the CLI flag `--telemetry` maps onto it. No flag, no ingestion.
- TelemetryCapability: describes what a bounded future table would hold
  (signals, resolution, projected volume) so activation is a documented
  decision, not an accident.

Nothing here writes data. The capability is surfaced in the catalog as
UNAVAILABLE for every session until Phase 6C deliberately changes that.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TelemetrySessionStatus(str, Enum):
    NOT_INGESTED = "NOT_INGESTED"          # canonical default: no telemetry rows exist
    INGESTED = "INGESTED"                  # Phase 6C: bounded rows exist for this session
    EXCLUDED = "EXCLUDED"                  # explicitly opted out for this session


# Signals a bounded Phase 6C table would carry (documented intent).
PLANNED_SIGNALS: tuple[str, ...] = (
    "speed", "throttle", "brake", "gear", "rpm", "drs", "x", "y", "distance", "time",
)

# Projected volume guard: full car-per-lap telemetry for one race session is
# on the order of 10^6-10^7 samples. Phase 6C must activate with per-session
# caps and a measured budget, not open-ended ingestion.
PROJECTED_SAMPLES_PER_SESSION = 2_000_000


@dataclass
class TelemetryPolicy:
    """Configuration for future telemetry ingestion. Default OFF."""

    enabled: bool = False
    session_codes: tuple[str, ...] = ("R", "Q")
    max_drivers_per_session: Optional[int] = None      # None = all
    max_laps_per_driver: Optional[int] = None          # None = all laps
    max_samples_per_session: int = PROJECTED_SAMPLES_PER_SESSION
    signals: tuple[str, ...] = PLANNED_SIGNALS

    def validate(self) -> list[str]:
        problems = []
        if self.enabled and self.max_samples_per_session > PROJECTED_SAMPLES_PER_SESSION:
            problems.append(
                f"max_samples_per_session {self.max_samples_per_session} exceeds the "
                f"documented budget {PROJECTED_SAMPLES_PER_SESSION}"
            )
        unknown = [s for s in self.signals if s not in PLANNED_SIGNALS]
        if unknown:
            problems.append(f"unknown signals: {unknown}")
        return problems


@dataclass
class TelemetryCapability:
    """Catalog-facing description of telemetry availability for a session."""

    session_id: str
    status: TelemetrySessionStatus = TelemetrySessionStatus.NOT_INGESTED
    policy: TelemetryPolicy = field(default_factory=TelemetryPolicy)

    @property
    def available(self) -> bool:
        """Honest availability: only INGESTED sessions have telemetry."""
        return self.status is TelemetrySessionStatus.INGESTED

    def describe(self) -> dict:
        return {
            "session_id": self.session_id,
            "status": self.status.value,
            "available": self.available,
            "policy_enabled": self.policy.enabled,
            "note": (
                "Telemetry ingestion is deferred to Phase 6C; no telemetry rows "
                "exist and none are fabricated."
            ),
        }
