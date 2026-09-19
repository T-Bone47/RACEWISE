"""Data availability: tracks what data is available from each provider by era/session."""
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


class AvailabilityStatus:
    SUPPORTED = "SUPPORTED"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass
class DataAvailability:
    """Tracks availability of a specific data type for a session."""
    provider: str
    entity_type: str  # e.g., "lap", "pit_stop", "weather", "telemetry"
    status: str  # SUPPORTED, PARTIAL, UNAVAILABLE, NOT_APPLICABLE
    records_available: int = 0
    records_expected: Optional[int] = None
    coverage_percentage: float = 0.0
    source_info: Optional[str] = None
    last_verified: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DataAvailability":
        return cls(**data)


@dataclass
class SessionAvailability:
    """Tracks data availability for a complete session."""
    season: int
    round: int
    grand_prix: str
    session_type: str  # R, Q, FP1, FP2, FP3, SQ, S
    provider: str
    entities: dict[str, DataAvailability] = field(default_factory=dict)
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "season": self.season,
            "round": self.round,
            "grand_prix": self.grand_prix,
            "session_type": self.session_type,
            "provider": self.provider,
            "entities": {k: v.to_dict() for k, v in self.entities.items()},
            "last_updated": self.last_updated,
        }

    def get_entity_status(self, entity_type: str) -> str:
        if entity_type in self.entities:
            return self.entities[entity_type].status
        return AvailabilityStatus.UNAVAILABLE

    def is_supported(self, entity_type: str) -> bool:
        status = self.get_entity_status(entity_type)
        return status == AvailabilityStatus.SUPPORTED


@dataclass
class SeasonAvailability:
    """Data availability summary for a season."""
    season: int
    rounds: int
    sessions_per_round: int
    providers: list[str]
    round_availability: dict[int, dict[str, SessionAvailability]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "season": self.season,
            "rounds": self.rounds,
            "sessions_per_round": self.sessions_per_round,
            "providers": self.providers,
            "round_availability": {
                str(k): {sk: sv.to_dict() for sk, sv in v.items()}
                for k, v in self.round_availability.items()
            },
        }


class AvailabilityIndex:
    """Central index of data availability across all providers and seasons."""

    def __init__(self, data_dir: Optional[str] = None) -> None:
        if data_dir is None:
            data_dir = os.environ.get("RACEWISE_DATA_DIR", str(Path.cwd() / "data"))
        self.data_dir = Path(data_dir)
        self.index_file = Path(data_dir) / "availability_index.json"
        self.index: dict[int, SeasonAvailability] = {}
        self._load()

    def _load(self) -> None:
        if self.index_file.exists():
            with open(self.index_file, "r") as f:
                data = json.load(f)
                for season_str, season_data in data.items():
                    season = int(season_str)
                    rounds = {}
                    for round_str, round_data in data[season_str].get("round_availability", {}).items():
                        round_num = int(round_str)
                        sessions = {}
                        for session_key, session_data in round_data.items():
                            provider = session_data["provider"]
                            entities = {}
                            for entity_key, entity_data in session_data.get("entities", {}).items():
                                entities[entity_key] = DataAvailability.from_dict(entity_data)
                            sessions[session_key] = SessionAvailability(
                                season=session_data["season"],
                                round=session_data["round"],
                                grand_prix=session_data["grand_prix"],
                                session_type=session_data["session_type"],
                                provider=provider,
                                entities=entities,
                                last_updated=session_data.get("last_updated", datetime.utcnow().isoformat()),
                            )
                        rounds[round_num] = {sk: sv for sk, sv in sessions.items()}
                    self.index[season] = SeasonAvailability(
                        season=season,
                        rounds=season_data["rounds"],
                        sessions_per_round=season_data["sessions_per_round"],
                        providers=season_data["providers"],
                        round_availability=rounds,
                    )

    def save(self) -> None:
        """Save availability index to disk."""
        data = {}
        for season, season_avail in self.index.items():
            round_data = {}
            for round_num, sessions in season_avail.round_availability.items():
                session_data = {}
                for session_key, session in sessions.items():
                    session_data = session.to_dict()
                    session_data["provider"] = session.provider
                    session_data["entities"] = {k: v.to_dict() for k, v in session.entities.items()}
                    session_data.pop("provider", None)
                    session_data.pop("entities", None)
                    session_data["season"] = session.season
                    session_data["round"] = session.round
                    session_data["grand_prix"] = session.grand_prix
                    session_data["session_type"] = session.session_type
                    session_data["provider"] = session.provider
                    session_data["entities"] = {k: v.to_dict() for k, v in session.entities.items()}
                    session_data["last_updated"] = session.last_updated
                    session_data = session.to_dict()
                    session_data[session_key] = session.to_dict()
                round_data[round_num] = session_data
            data[season] = {
                "season": season_avail.season,
                "rounds": season_avail.rounds,
                "sessions_per_round": season_avail.sessions_per_round,
                "providers": season_avail.providers,
                "round_availability": round_data,
            }
        with open(self.index_file, "w") as f:
            json.dump(data, f, indent=2)

    def record_availability(
        self,
        season: int,
        round_num: int,
        grand_prix: str,
        session_type: str,
        provider: str,
        entity_type: str,
        status: str,
        records_available: int = 0,
        records_expected: Optional[int] = None,
        source_info: Optional[str] = None,
        notes: str = "",
    ) -> None:
        """Record data availability for a specific entity."""
        if season not in self.index:
            self.index[season] = SeasonAvailability(
                season=season,
                rounds=0,
                sessions_per_round=0,
                providers=[],
            )

        season_avail = self.index[season]

        if round_num not in season_avail.round_availability:
            season_avail.round_availability[round_num] = {}
            season_avail.rounds += 1

        session_key = f"{provider}_{session_type}"
        if session_key not in season_avail.round_availability[round_num]:
            season_avail.round_availability[round_num][session_key] = SessionAvailability(
                season=season,
                round=round_num,
                grand_prix=season,  # Will be updated
                session_type=session_type,
                provider=provider,
            )
            season_avail.sessions_per_round += 1
            if provider not in season_avail.providers:
                season_avail.providers.append(provider)

        session = season_avail.round_availability[round_num][session_key]
        session.grand_prix = session.grand_prix or grand_prix
        session.last_updated = datetime.utcnow().isoformat()

        if entity_type not in session.entities:
            session.entities[entity_type] = DataAvailability(
                provider=provider,
                entity_type=entity_type,
            )

        entity = session.entities[entity_type]
        entity.status = status
        entity.records_available = records_available
        entity.records_expected = records_expected
        entity.coverage_percentage = (
            (records_available / records_expected * 100) if records_expected else 0.0
        )
        entity.source_info = source_info
        entity.notes = notes
        entity.last_verified = datetime.utcnow().isoformat()

    def get_session_availability(
        self,
        season: int,
        round_num: int,
        session_type: str,
    ) -> Optional[dict[str, SessionAvailability]]:
        """Get availability for all providers for a session."""
        if season not in self.index:
            return None
        if round_num not in self.index[season].round_availability:
            return None

        result = {}
        for session_key, session in self.index[season].round_availability[round_num].items():
            if session.session_type == session_type:
                result[session.provider] = session
        return result if result else None

    def get_coverage_matrix(self) -> dict:
        """Generate a coverage matrix for all seasons."""
        matrix = {}
        for season, season_avail in sorted(self.index.items()):
            season_data = {
                "rounds": season_avail.rounds,
                "sessions": season_avail.sessions_per_round,
                "providers": season_avail.providers,
                "rounds_detail": {},
            }
            for round_num, sessions in season_avail.round_availability.items():
                round_data = {}
                for session_key, session in sessions.items():
                    entity_status = {}
                    for entity_type, entity in session.entities.items():
                        entity_status[entity_type] = entity.status
                    round_data[session.session_type] = {
                        "provider": session.provider,
                        "entities": entity_status,
                    }
                season_data["rounds_detail"][round_num] = round_data
            matrix[season] = season_data
        return matrix


@lru_cache(maxsize=4)
def get_availability_index(data_dir: Optional[str] = None) -> AvailabilityIndex:
    return AvailabilityIndex(data_dir)