"""Phase 6T benchmark runner: autonomous investigations.

Executes the corpus in
tests/benchmarks/phase_6t_autonomous_investigations.json through the real
orchestrator (intake -> lifecycle -> engine -> memory), records structured
results with per-stage timings, and verifies deterministic identities.
Structural assertions only - statuses, stage coverage, evidence presence,
determinism - never invented numeric answers.

Usage:
    python tests/benchmarks/run_autonomous_benchmark.py \
        [--corpus tests/benchmarks/phase_6t_autonomous_investigations.json] \
        [--out data/benchmarks/6t_benchmark_results.json] \
        [--limit N] [--only T01,T02] [--skip-api]

The runner always writes a results file (exit code 0 when the corpus
executed to completion, 1 only if the corpus itself could not be executed).
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from racewise.data.historical.autonomous_investigator import (  # noqa: E402
    run_autonomous_investigation,
)
from racewise.data.historical.canonical_queries import (  # noqa: E402
    CanonicalQueries, get_canonical_queries,
)

CORPUS_DEFAULT = ROOT / "tests" / "benchmarks" / \
    "phase_6t_autonomous_investigations.json"
RESULTS_DEFAULT = ROOT / "data" / "benchmarks" / "6t_benchmark_results.json"
DB_PATH = ROOT / "data" / "canonical" / "canonical.db"


def _load_corpus(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = [c["benchmark_id"] for c in data["cases"]]
    if len(set(ids)) != len(ids):
        raise SystemExit("corpus contains duplicate benchmark_id values")
    return data


def _run_stage_timings(queries: CanonicalQueries, question: str,
                       context: dict[str, Any],
                       constraints: dict[str, Any]) -> tuple[dict, list]:
    """Run with a stage callback recording inter-stage timings."""
    stage_times: list[dict[str, Any]] = []
    last = time.perf_counter()

    def on_stage(entry: dict[str, Any]) -> None:
        nonlocal last
        now = time.perf_counter()
        stage_times.append({"stage": entry["stage"],
                            "status": entry["status"],
                            "delta_ms": round((now - last) * 1000, 2)})
        last = now

    run = run_autonomous_investigation(
        queries, question, context=context, constraints=constraints,
        on_stage=on_stage)
    return run, stage_times


def run_case(queries: CanonicalQueries, case: dict[str, Any],
             api_url: str | None) -> dict[str, Any]:
    t0 = time.perf_counter()
    expect = case.get("expect", {})
    checks: dict[str, Any] = {}

    context = dict(case.get("context") or {})
    constraints = dict(case.get("constraints") or {})
    run, stage_times = _run_stage_timings(
        queries, case["question"], context, constraints)

    status = run.get("status")
    ok = status in expect.get("status", [status])

    # determinism re-run (same process)
    if expect.get("deterministic"):
        run2 = run_autonomous_investigation(
            queries, case["question"], dict(case.get("context") or {}),
            dict(case.get("constraints") or {}))
        checks["deterministic"] = (
            run2.get("run_id") == run.get("run_id")
            and run2.get("decision_trace") == run.get("decision_trace"))
        ok = ok and checks["deterministic"]

    # question-type classification
    qt_expect = expect.get("question_type")
    if qt_expect:
        qt_actual = (run.get("question") or {}).get("question_type")
        checks["question_type"] = qt_actual
        if status in ("COMPLETED", "DATA_UNAVAILABLE",
                      "INSUFFICIENT_EVIDENCE"):
            ok = ok and qt_actual == qt_expect

    # decision-trace floor
    min_dec = expect.get("min_decisions")
    if min_dec:
        n = len(run.get("decision_trace") or [])
        checks["decisions"] = n
        ok = ok and n >= min_dec

    # required completed stages
    for stage in expect.get("requires_stage", []):
        done = any(s["stage"] == stage and s["status"] == "COMPLETED"
                   for s in run.get("stage_ledger") or [])
        checks[f"stage_{stage}"] = done
        ok = ok and done

    # honest failure reason
    reason_sub = expect.get("limitation_reason_contains")
    if reason_sub:
        checks["reason"] = (run.get("reason") or "")[:160]
        ok = ok and reason_sub in (run.get("reason") or "")

    # injection quarantine with unchanged deterministic outcome
    if expect.get("injection_flagged"):
        flagged = bool((run.get("injection_scan") or {}).get("flagged"))
        checks["injection_flagged"] = flagged
        ok = ok and flagged
    neutral_ref = expect.get("deterministic_output_matches_neutral")
    if neutral_ref:
        neutral_case = next(c for c in CORPUS_CACHE["cases"]
                            if c["benchmark_id"] == neutral_ref)
        neutral = run_autonomous_investigation(
            queries, neutral_case["question"],
            dict(neutral_case.get("context") or {}),
            dict(neutral_case.get("constraints") or {}))
        same = (run.get("engine_result_ref") or {}).get("output_hash") == \
            (neutral.get("engine_result_ref") or {}).get("output_hash")
        checks["output_matches_neutral"] = same
        ok = ok and same

    # every completed run must embed a VALID engine result
    if status == "COMPLETED":
        ref = run.get("engine_result_ref") or {}
        checks["engine_valid"] = ref.get("status") == "VALID"
        ok = ok and checks["engine_valid"]
        checks["memory_derived"] = (run.get("memory") or {}).get(
            "items_derived", 0) >= 0

    return {
        "benchmark_id": case["benchmark_id"],
        "category": case["category"],
        "limitation_case": case.get("limitation_case"),
        "status": status,
        "failed_stage": run.get("failed_stage"),
        "run_id": run.get("run_id"),
        "engine_investigation_id": (run.get("engine_result_ref") or {}).get(
            "investigation_id"),
        "pass": ok,
        "checks": checks,
        "stage_timings": stage_times,
        "total_ms": run.get("metrics", {}).get("total_runtime_ms"),
        "elapsed_s": round(time.perf_counter() - t0, 3),
    }


CORPUS_CACHE: dict[str, Any] = {}


def main() -> int:
    global CORPUS_CACHE
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, default=CORPUS_DEFAULT)
    ap.add_argument("--out", type=Path, default=RESULTS_DEFAULT)
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="")
    ap.add_argument("--skip-api", action="store_true",
                    help="accepted for runner-contract parity; the 6T "
                         "chain itself never calls the API")
    args = ap.parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"canonical DB not present at {DB_PATH}")

    corpus = _load_corpus(args.corpus)
    CORPUS_CACHE = corpus
    cases = corpus["cases"]
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        cases = [c for c in cases if c["benchmark_id"] in wanted]
    if args.limit:
        cases = cases[: int(args.limit)]

    queries = get_canonical_queries()
    results = []
    t_all = time.perf_counter()
    for case in cases:
        result = run_case(queries, case, None if args.skip_api else args.api)
        results.append(result)
        mark = "PASS" if result["pass"] else "FAIL"
        print(f"[{mark}] {result['benchmark_id']} {result['category']:12s} "
              f"status={result['status']}")
    wall = round(time.perf_counter() - t_all, 1)

    n_pass = sum(1 for r in results if r["pass"])
    totals = [r["total_ms"] for r in results if r.get("total_ms")]

    def pct(values: list[float], p: float) -> float:
        return round(statistics.quantiles(values, n=100)[int(p) - 1]
                     if len(values) > 1 else values[0], 1) if values else 0.0

    stage_deltas: dict[str, list[float]] = {}
    for r in results:
        for st in r.get("stage_timings") or []:
            stage_deltas.setdefault(st["stage"], []).append(st["delta_ms"])

    out = {
        "benchmark": "phase_6t_autonomous_investigations",
        "benchmark_version": corpus["version"],
        "corpus_path": str(args.corpus.relative_to(ROOT)),
        "corpus_size": len(cases),
        "passed": n_pass,
        "failed": len(results) - n_pass,
        "wall_s": wall,
        "runtime_performance": {
            "full_run_ms": {"p50": pct(totals, 50), "p95": pct(totals, 95),
                            "max": max(totals) if totals else 0.0},
            "stage_delta_ms": {
                stage: {"p50": pct(v, 50), "p95": pct(v, 95),
                        "max": max(v)}
                for stage, v in sorted(stage_deltas.items())},
        },
        "results": results,
        "provenance": {
            "method": "deterministic_autonomous_orchestration_benchmark",
            "orchestrator": "6t_orchestrator_v1",
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\n{n_pass}/{len(results)} passed "
          f"({len(results) - n_pass} failed) in {wall}s")
    print(f"results: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
