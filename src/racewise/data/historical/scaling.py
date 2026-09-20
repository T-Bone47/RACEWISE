"""Scalable FastF1 modern-data ingestion (Phase 6B).

Extends the Phase 6A canonicalizer with a controlled, resumable,
observable season-ingestion engine. Design properties:

- Priority levels: RACE first, QUALIFYING second, SPRINT/SQ third,
  practice only on explicit request (documented scope).
- Checkpoints: per (season, round, session code) with stage, status and
  row counts; safely resumable after interruption.
- Failure isolation: one failed session never aborts a season; failures
  are collected into an explicit machine-readable report.
- Validation gates: every ingested session passes FK + provenance +
  identity checks; failures are marked FAILED_VALIDATION, not persisted
  silently.
- Observability: per-session metrics (run id, timings, rows, cache hits,
  errors) exported as JSON alongside the existing ingestion state.

Phase 6B does NOT ingest channel telemetry; see telemetry_policy.py.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Session priority levels (scope documented in PHASE_6B report).
PRIORITY_LEVELS: dict[str, list[str]] = {
    1: ["R"],
    2: ["Q"],
    3: ["S", "SQ"],
    4: ["FP1", "FP2", "FP3"],
}

# Map actual schedule session names (fastf1 EventSchedule Session1..Session5)
# to FastF1 session codes. Discovery never invents sessions: only names the
# provider's own schedule lists for an event are enumerated.
SESSION_NAME_TO_CODE: dict[str, str] = {
    "Practice 1": "FP1",
    "Practice 2": "FP2",
    "Practice 3": "FP3",
    "Practice 4": "FP4",
    "Qualifying": "Q",
    "Sprint Qualifying": "SQ",
    "Sprint Shootout": "SQ",
    "Sprint": "S",
    "Race": "R",
}

SCALING_TRANSFORMATION_VERSION = "2.0"

# FastF1's limiter is 500 calls/hour shared across ALL processes hitting the
# API. When tripped mid-run, back off exponentially (the quota window is long,
# so hammering retries only burns capacity and starves parallel runs) and cap
# the attempts per session; exceeded cap => FAILED_PROVIDER with the reason.
RATE_LIMIT_PAUSE_SECONDS = 90
RATE_LIMIT_MAX_RETRIES = 4


@dataclass
class SessionOutcome:
    """Outcome of one session's ingestion attempt."""
    season: int
    event_name: str
    round_number: int
    session_code: str
    status: str  # SUCCESS | UNAVAILABLE | FAILED_VALIDATION | FAILED_PROVIDER | SKIPPED_NO_SESSION
    rows: dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None
    load_seconds: float = 0.0
    canonicalize_seconds: float = 0.0
    cache_hit: Optional[bool] = None
    run_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": "fastf1",
            "season": self.season,
            "event": self.event_name,
            "round": self.round_number,
            "session": self.session_code,
            "status": self.status,
            "rows": self.rows,
            "error": self.error,
            "load_seconds": round(self.load_seconds, 2),
            "canonicalize_seconds": round(self.canonicalize_seconds, 2),
            "cache_hit": self.cache_hit,
            "run_id": self.run_id,
        }


@dataclass
class SeasonReport:
    """Per-season ingestion report (machine-readable)."""
    season: int
    run_id: str
    started_at: str
    finished_at: Optional[str] = None
    discovered: int = 0
    outcomes: list[SessionOutcome] = field(default_factory=list)
    runtime_seconds: float = 0.0

    def summary(self) -> dict[str, Any]:
        by_status: dict[str, int] = {}
        for o in self.outcomes:
            by_status[o.status] = by_status.get(o.status, 0) + 1
        rows_total: dict[str, int] = {}
        for o in self.outcomes:
            for k, v in o.rows.items():
                rows_total[k] = rows_total.get(k, 0) + v
        return {
            "season": self.season,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "sessions_discovered": self.discovered,
            "sessions": {
                "success": by_status.get("SUCCESS", 0),
                "unavailable": by_status.get("UNAVAILABLE", 0)
                + by_status.get("SKIPPED_NO_SESSION", 0),
                "failed_validation": by_status.get("FAILED_VALIDATION", 0),
                "failed_provider": by_status.get("FAILED_PROVIDER", 0),
            },
            "rows": rows_total,
            "runtime_seconds": round(self.runtime_seconds, 1),
        }


class FastF1SeasonIngester:
    """Resumable, failure-isolated season ingestion over the canonical store."""

    def __init__(
        self,
        canonicalizer: Any,
        cache_dir: Optional[str] = None,
        state_dir: Optional[str] = None,
        validator: Any = None,
        telemetry_policy: Any = None,
    ) -> None:
        from racewise.data.fastf1_adapter import FastF1Adapter
        from racewise.data.historical.validators import CanonicalDataValidator

        self.adapter = FastF1Adapter(cache_dir=cache_dir)
        self.canon = canonicalizer
        self.validator = validator or CanonicalDataValidator()
        self.telemetry_policy = telemetry_policy
        self.state_dir = Path(state_dir) if state_dir else Path.cwd() / "data" / "ingestion_state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_file = self.state_dir / "fastf1_scaling_checkpoints.json"
        self.checkpoints = self._load_json(self.checkpoint_file) or {}

    # -- checkpoint primitives -------------------------------------------------

    @staticmethod
    def _load_json(path: Path) -> Any:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning(f"Corrupt checkpoint file {path}; starting fresh")
        return None

    def _ck_key(self, season: int, round_number: int, code: str) -> str:
        return f"{season}:{round_number}:{code}"

    def is_done(self, season: int, round_number: int, code: str) -> bool:
        entry = self.checkpoints.get(self._ck_key(season, round_number, code))
        return bool(entry and entry.get("status") in ("SUCCESS", "UNAVAILABLE", "SKIPPED_NO_SESSION"))

    def set_checkpoint(self, outcome: SessionOutcome, stage: str = "canonicalization") -> None:
        self.checkpoints[self._ck_key(outcome.season, outcome.round_number, outcome.session_code)] = {
            "provider": "fastf1",
            "season": outcome.season,
            "event": outcome.event_name,
            "session": outcome.session_code,
            "stage": stage,
            "status": outcome.status,
            "rows": outcome.rows,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "error": outcome.error,
        }
        self._save_checkpoints()

    def _save_checkpoints(self) -> None:
        self.checkpoint_file.write_text(
            json.dumps(self.checkpoints, indent=2), encoding="utf-8"
        )

    # -- schedule discovery ------------------------------------------------------

    def discover_season(self, season: int, priority_levels: Optional[list[int]] = None) -> list[dict]:
        """Enumerate supported sessions for a season from the real schedule.

        Only sessions the provider's own schedule lists for an event are
        returned (name-mapped via SESSION_NAME_TO_CODE); sprint sessions are
        therefore never fabricated for non-sprint weekends.
        """
        import fastf1

        levels = priority_levels or [1, 2, 3]
        wanted = {c for lvl in levels for c in PRIORITY_LEVELS[lvl]}
        schedule = fastf1.get_event_schedule(season, include_testing=False)
        sessions: list[dict] = []
        for row in schedule.itertuples(index=False):
            event_codes: list[str] = []
            for i in range(1, 6):
                name = getattr(row, f"Session{i}", None)
                code = SESSION_NAME_TO_CODE.get(str(name)) if name else None
                if code and code in wanted:
                    event_codes.append(code)
            for code in event_codes:
                sessions.append(
                    {
                        "season": season,
                        "event_name": str(row.EventName),
                        "round_number": int(row.RoundNumber),
                        "session_code": code,
                    }
                )
        return sessions

    # -- ingestion ----------------------------------------------------------------

    def ingest_season(
        self,
        season: int,
        priority_levels: Optional[list[int]] = None,
        rounds: Optional[list[int]] = None,
        resume: bool = True,
        force: bool = False,
    ) -> SeasonReport:
        """Ingest one season with checkpoints and failure isolation."""
        run_id = f"ff1-{season}-{uuid.uuid4().hex[:8]}"
        started_at = datetime.now(timezone.utc).isoformat()
        t_start = time.perf_counter()
        report = SeasonReport(season=season, run_id=run_id, started_at=started_at)

        targets = self.discover_season(season, priority_levels)
        if rounds:
            targets = [t for t in targets if t["round_number"] in rounds]
        report.discovered = len(targets)

        for target in targets:
            season_n = target["season"]
            round_n = target["round_number"]
            code = target["session_code"]
            if resume and not force and self.is_done(season_n, round_n, code):
                ck = self.checkpoints[self._ck_key(season_n, round_n, code)]
                report.outcomes.append(
                    SessionOutcome(
                        season=season_n, event_name=ck.get("event", target["event_name"]),
                        round_number=round_n, session_code=code,
                        status="SUCCESS" if ck["status"] == "SUCCESS" else ck["status"],
                        rows=ck.get("rows", {}), run_id=run_id,
                    )
                )
                continue
            outcome = self._ingest_session(target, run_id)
            # FastF1's own limiter (fastf1.req.RateLimitExceededError, "any API:
            # 500 calls/h", shared across all processes) trips mid-season.
            # Back off exponentially and retry the same session a bounded
            # number of times; persisting the failure reason beats silently
            # burning the remaining schedule as FAILED_PROVIDER.
            retry = 0
            while (
                outcome.status == "FAILED_PROVIDER"
                and outcome.error
                and "RateLimit" in outcome.error
                and retry < RATE_LIMIT_MAX_RETRIES
            ):
                retry += 1
                wait_s = RATE_LIMIT_PAUSE_SECONDS * (2 ** (retry - 1))
                logger.warning(
                    "[%s R%s %s] rate limit hit; backing off %ss (retry %s/%s)",
                    season_n, round_n, code, wait_s, retry, RATE_LIMIT_MAX_RETRIES,
                )
                time.sleep(wait_s)
                outcome = self._ingest_session(target, run_id)
            report.outcomes.append(outcome)
            self.set_checkpoint(outcome)
            logger.info(f"[{season_n} R{round_n} {code}] {outcome.status} rows={outcome.rows}")

        report.runtime_seconds = time.perf_counter() - t_start
        report.finished_at = datetime.now(timezone.utc).isoformat()
        self._write_season_report(report)
        return report

    def _ingest_session(self, target: dict, run_id: str) -> SessionOutcome:
        """Load, canonicalize and validate one session. Never raises."""
        outcome = SessionOutcome(
            season=target["season"],
            event_name=target["event_name"],
            round_number=target["round_number"],
            session_code=target["session_code"],
            status="FAILED_PROVIDER",
            run_id=run_id,
        )
        t0 = time.perf_counter()
        try:
            session = self.adapter.load_session(
                target["season"], target["round_number"], target["session_code"]
            )
        except Exception as e:
            outcome.load_seconds = time.perf_counter() - t0
            msg = f"{type(e).__name__}: {e}"
            outcome.error = msg[:300]
            # Distinguish "provider has no such session/data" from real failures.
            lowered = msg.lower()
            if (
                "out of bounds" in lowered
                or "no matching" in lowered
                or "404" in msg
                or "does not exist for this event" in lowered
            ):
                outcome.status = "UNAVAILABLE"
            return outcome
        outcome.load_seconds = time.perf_counter() - t0

        t1 = time.perf_counter()
        try:
            result = self.canon.ingest_session(
                target["season"], target["round_number"], target["session_code"], session,
                telemetry_policy=self.telemetry_policy,
            )
        except Exception as e:
            outcome.canonicalize_seconds = time.perf_counter() - t1
            outcome.status = "FAILED_PROVIDER"
            outcome.error = f"canonicalize {type(e).__name__}: {e}"[:300]
            return outcome
        outcome.canonicalize_seconds = time.perf_counter() - t1

        if not result.get("attached"):
            outcome.status = "SKIPPED_NO_SESSION"
            outcome.error = "F1DB does not represent this session"
            return outcome

        outcome.rows = {
            "stints": result.get("stints", 0),
            "weather": result.get("weather", 0),
            "race_control": result.get("race_control", 0),
            "lap_rows": result.get("lap_rows", 0),
            **({"telemetry_samples": result["telemetry"]["samples"]}
               if result.get("telemetry") else {}),
        }
        # Validation gate: a session with rows must not violate store invariants.
        problems = self._validate_after()
        if problems:
            outcome.status = "FAILED_VALIDATION"
            outcome.error = "; ".join(problems)[:300]
            return outcome
        outcome.status = "SUCCESS"
        return outcome

    def _validate_after(self) -> list[str]:
        """Post-ingestion validation gate over the whole store."""
        report = self.validator.validate_all()
        return report.failures

    def _write_season_report(self, report: SeasonReport) -> None:
        path = self.state_dir / f"fastf1_scaling_report_{report.season}.json"
        payload = report.summary()
        payload["outcomes"] = [o.to_dict() for o in report.outcomes]
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def ingest_seasons(
    seasons: list[int],
    priority_levels: Optional[list[int]] = None,
    rounds: Optional[list[int]] = None,
    resume: bool = True,
    force: bool = False,
    telemetry_policy: Any = None,
) -> list[dict]:
    """Ingest multiple seasons; returns per-season summaries (never raises).

    telemetry_policy: optional TelemetryPolicy. Default None = telemetry OFF;
    an *enabled* policy opts the run into bounded telemetry ingestion.
    """
    from racewise.data.historical.f1db_canonical import CanonicalStore
    from racewise.data.historical.fastf1_canonical import FastF1Canonicalizer

    store = CanonicalStore()
    canon = FastF1Canonicalizer(store)
    ingester = FastF1SeasonIngester(canon, telemetry_policy=telemetry_policy)
    summaries = []
    for season in seasons:
        try:
            report = ingester.ingest_season(
                season, priority_levels=priority_levels, rounds=rounds,
                resume=resume, force=force,
            )
            summaries.append(report.summary())
        except Exception as e:
            logger.error(f"Season {season} ingestion framework error: {e}")
            summaries.append({"season": season, "error": str(e)[:300]})
        # Availability catalog must track newly ingested data after each season.
        try:
            canon._f1db.rebuild_catalog()
        except Exception as e:
            logger.error(f"Catalog rebuild failed after {season}: {e}")
    return summaries
