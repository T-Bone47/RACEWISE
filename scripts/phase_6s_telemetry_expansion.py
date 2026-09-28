"""Phase 6S GAP 3: bounded telemetry probe expansion 12 -> 24 laps/driver.

Re-ingests the already-telemetry-covered RACE sessions under the raised
policy bound. Strictly additive (content-addressed idempotent upsert, no
deletes), resumable, and bounded per session by the unchanged sample
budget. Progress is checkpointed to data/ingestion_state/.

Usage: python scripts/phase_6s_telemetry_expansion.py [--limit N]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

STATE_PATH = REPO / "data" / "ingestion_state" / "phase_6s_telemetry_expansion.json"


def covered_sessions() -> list[tuple[int, int]]:
    """The 6D telemetry-covered RACE sessions (from the canonical store)."""
    from racewise.data.historical.f1db_canonical import CanonicalStore

    store = CanonicalStore()
    with store._conn() as conn:
        rows = conn.execute(
            """
            SELECT ra.season, ra.round
            FROM canonical_telemetry t
            JOIN canonical_sessions s ON s.session_id = t.session_id
            JOIN canonical_races ra ON ra.race_id = s.race_id
            WHERE s.session_type = 'RACE'
            GROUP BY s.session_id
            ORDER BY ra.season, ra.round
            """
        ).fetchall()
    return [(int(r["season"]), int(r["round"])) for r in rows]


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"completed": {}, "sessions": []}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Process at most N sessions this run")
    parser.add_argument("--stop-on-rate-limit", action="store_true",
                        help="Stop this run when the provider hourly "
                             "rate limit is hit (resume later; state is "
                             "checkpointed per session)")
    args = parser.parse_args()

    from racewise.data.fastf1_adapter import FastF1Adapter, enable_cache
    from racewise.data.historical.fastf1_canonical import (
        FastF1Canonicalizer,
    )
    from racewise.data.historical.f1db_canonical import CanonicalStore
    from racewise.data.historical.telemetry_policy import TelemetryPolicy

    enable_cache(str(REPO / ".fastf1-cache"))
    adapter = FastF1Adapter(cache_dir=str(REPO / ".fastf1-cache"))
    store = CanonicalStore()
    canon = FastF1Canonicalizer(store)
    policy = TelemetryPolicy(enabled=True)
    problems = policy.validate()
    if problems:
        print("Invalid telemetry policy:", problems)
        return 1

    sessions = covered_sessions()
    state = load_state()
    state["sessions"] = [list(s) for s in sessions]
    done = state.get("completed", {})

    todo = [(s, r) for s, r in sessions
            if done.get(f"{s}-{r}", {}).get("status") != "completed"]
    if args.limit:
        todo = todo[: args.limit]

    print(f"covered sessions: {len(sessions)}; remaining: {len(todo)}")
    t_start = time.perf_counter()
    failures = 0
    for i, (season, round_num) in enumerate(todo, start=1):
        key = f"{season}-{round_num}"
        t0 = time.perf_counter()
        try:
            session = adapter.load_session(season, round_num, "R")
            res = canon.ingest_session(season, round_num, "R", session,
                                       telemetry_policy=policy)
            stats = res.get("telemetry") or {}
            done[key] = {
                "status": "completed",
                "laps": stats.get("laps"),
                "samples": stats.get("samples"),
                "truncated": stats.get("truncated_to_cap"),
                "seconds": round(time.perf_counter() - t0, 1),
            }
            state["completed"] = done
            save_state(state)
            print(f"[{i}/{len(todo)}] {season} R{round_num}: "
                  f"laps={stats.get('laps')} samples={stats.get('samples')} "
                  f"truncated={stats.get('truncated_to_cap')} "
                  f"({done[key]['seconds']}s)", flush=True)
        except Exception as exc:  # noqa: BLE001 - per-session isolation
            failures += 1
            done[key] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            state["completed"] = done
            save_state(state)
            print(f"[{i}/{len(todo)}] {season} R{round_num}: FAILED "
                  f"({type(exc).__name__}: {exc})", flush=True)
            if args.stop_on_rate_limit and "RateLimitExceeded" in \
                    type(exc).__name__:
                print("rate limit hit; stopping this run (resume with the "
                      "same command)", flush=True)
                break

    print(f"done in {round(time.perf_counter() - t_start, 1)}s; "
          f"failures={failures}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
