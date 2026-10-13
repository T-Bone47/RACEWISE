"""RACEWISE Frontier Evaluation Report Generator.

Runs the full evaluation suite (engineering benchmark + question engine benchmark)
and produces a structured, reproducible report comparing against a baseline.

Usage:
    python scripts/evaluation_report.py [--baseline PATH] [--output PATH]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def run_engineering_benchmark() -> dict[str, Any]:
    """Run the engineering benchmark and return parsed results."""
    script = ROOT / "tests" / "benchmarks" / "run_engineering_benchmark.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--out", str(ROOT / "data" / "benchmarks" / "frontier_eval_engineering.json")],
        capture_output=True, text=True, timeout=600, cwd=str(ROOT),
    )
    if proc.returncode != 0:
        return {"error": proc.stderr[-500:], "pass": False}
    results_path = ROOT / "data" / "benchmarks" / "frontier_eval_engineering.json"
    if results_path.exists():
        return json.loads(results_path.read_text(encoding="utf-8"))
    return {"error": "results file not found", "pass": False}


def run_question_engine_benchmark() -> dict[str, Any]:
    """Run the question engine benchmark and return parsed results."""
    # The question engine benchmark is run via pytest
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/benchmarks/run_engineering_benchmark.py", "-q", "--tb=short"],
        capture_output=True, text=True, timeout=300, cwd=str(ROOT),
    )
    # Parse the output for pass/fail counts
    lines = proc.stdout.strip().split("\n")
    summary_line = [l for l in lines if "passed" in l or "failed" in l]
    return {
        "pytest_output": proc.stdout[-2000:],
        "returncode": proc.returncode,
        "pass": proc.returncode == 0,
    }


def run_benchmark_questions() -> dict[str, Any]:
    """Run the 23-question benchmark and return results."""
    script = ROOT / "tests" / "benchmark" / "run_benchmark.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True, timeout=300, cwd=str(ROOT),
    )
    results_path = ROOT / "benchmark_results.json"
    if results_path.exists():
        return json.loads(results_path.read_text(encoding="utf-8"))
    return {"error": "benchmark_results.json not found", "pass": False}


def run_frontend_tests() -> dict[str, Any]:
    """Run frontend tests and return results."""
    proc = subprocess.run(
        ["npx", "vitest", "run", "--reporter=verbose"],
        capture_output=True, text=True, timeout=300, cwd=str(ROOT / "apps" / "web"),
    )
    lines = proc.stdout.strip().split("\n")
    test_summary = [l for l in lines if "Test Files" in l or "Tests" in l]
    return {
        "output_tail": proc.stdout[-2000:],
        "test_summary": test_summary,
        "pass": proc.returncode == 0,
    }


def analyze_engineering_results(results: dict[str, Any]) -> dict[str, Any]:
    """Analyze engineering benchmark results."""
    if not results.get("pass"):
        return {"error": results.get("error", "benchmark failed"), "pass": False}

    cases = results.get("cases", [])
    total = len(cases)
    passed = sum(1 for c in cases if c.get("pass"))
    failed = total - passed

    # Categorize failures
    failures_by_category: dict[str, list[dict]] = {}
    for c in cases:
        if not c.get("pass"):
            cat = c.get("category_name", "unknown")
            failures_by_category.setdefault(cat, []).append(c)

    # Kind breakdown
    kinds = {}
    for c in cases:
        kind = c.get("kind", "unknown")
        kinds[kind] = kinds.get(kind, 0) + 1

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / total, 4) if total else 0,
        "failures_by_category": {k: len(v) for k, v in failures_by_category.items()},
        "kind_breakdown": kinds,
        "failure_details": [
            {
                "benchmark_id": c.get("benchmark_id"),
                "category": c.get("category_name"),
                "kind": c.get("kind"),
                "detail": c.get("detail", ""),
            }
            for c in cases if not c.get("pass")
        ],
    }


def generate_report(
    engineering: dict[str, Any],
    questions: dict[str, Any],
    frontend: dict[str, Any],
    baseline_path: Path | None,
) -> dict[str, Any]:
    """Generate the full evaluation report."""
    report: dict[str, Any] = {
        "report_version": "frontier_eval_v1",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "commit": _get_git_commit(),
        "engineering_benchmark": engineering,
        "benchmark_questions": questions,
        "frontend_tests": frontend,
    }

    # Compare against baseline if provided
    if baseline_path and baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        report["baseline_comparison"] = _compare_to_baseline(report, baseline)

    return report


def _get_git_commit() -> str:
    """Get the current git commit hash."""
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def _compare_to_baseline(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """Compare current results to baseline."""
    comparison: dict[str, Any] = {}

    # Engineering benchmark comparison
    cur_eng = current.get("engineering_benchmark", {})
    base_eng = baseline.get("engineering_benchmark", {})
    if cur_eng and base_eng:
        cur_pass = cur_eng.get("passed", 0)
        base_pass = base_eng.get("passed", 0)
        comparison["engineering_benchmark"] = {
            "baseline_pass": base_pass,
            "current_pass": cur_pass,
            "delta": cur_pass - base_pass,
            "baseline_total": base_eng.get("total", 0),
            "current_total": cur_eng.get("total", 0),
        }

    # Benchmark questions comparison
    cur_q = current.get("benchmark_questions", {})
    base_q = baseline.get("benchmark_questions", {})
    if cur_q and base_q:
        cur_completed = cur_q.get("summary", {}).get("completed", 0)
        base_completed = base_q.get("summary", {}).get("completed", 0)
        comparison["benchmark_questions"] = {
            "baseline_completed": base_completed,
            "current_completed": cur_completed,
            "delta": cur_completed - base_completed,
        }

    return comparison


def main() -> None:
    parser = argparse.ArgumentParser(description="RACEWISE Frontier Evaluation Report")
    parser.add_argument("--baseline", type=Path, default=None, help="Path to baseline report JSON")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "benchmarks" / "frontier_eval_report.json")
    parser.add_argument("--skip-engineering", action="store_true", help="Skip engineering benchmark (slow)")
    parser.add_argument("--skip-frontend", action="store_true", help="Skip frontend tests")
    args = parser.parse_args()

    print("RACEWISE Frontier Evaluation Report")
    print("=" * 50)

    # Run engineering benchmark
    if not args.skip_engineering:
        print("\n[1/3] Running engineering benchmark...")
        eng_start = time.time()
        eng_results = run_engineering_benchmark()
        eng_analysis = analyze_engineering_results(eng_results)
        print(f"  Engineering: {eng_analysis.get('passed', 0)}/{eng_analysis.get('total', 0)} passed "
              f"({eng_analysis.get('pass_rate', 0):.1%}) [{time.time() - eng_start:.1f}s]")
    else:
        eng_analysis = {"skipped": True}

    # Run benchmark questions
    print("\n[2/3] Running benchmark questions...")
    q_start = time.time()
    q_results = run_benchmark_questions()
    print(f"  Benchmark questions: {q_results.get('summary', {}).get('completed', 0)}/"
          f"{q_results.get('summary', {}).get('n_questions', 0)} completed [{time.time() - q_start:.1f}s]")

    # Run frontend tests
    if not args.skip_frontend:
        print("\n[3/3] Running frontend tests...")
        fe_start = time.time()
        fe_results = run_frontend_tests()
        print(f"  Frontend: {'PASS' if fe_results.get('pass') else 'FAIL'} [{time.time() - fe_start:.1f}s]")
    else:
        fe_results = {"skipped": True}

    # Generate report
    print("\nGenerating report...")
    baseline = args.baseline
    report = generate_report(eng_analysis, q_results, fe_results, baseline)

    # Write report
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport written to: {args.output}")

    # Print summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"Engineering benchmark: {eng_analysis.get('passed', 0)}/{eng_analysis.get('total', 0)} "
          f"({eng_analysis.get('pass_rate', 0):.1%})")
    print(f"Benchmark questions: {q_results.get('summary', {}).get('completed', 0)}/"
          f"{q_results.get('summary', {}).get('n_questions', 0)} completed")
    print(f"Frontend tests: {'PASS' if fe_results.get('pass') else 'FAIL'}")

    if "baseline_comparison" in report:
        print("\nBaseline comparison:")
        for key, val in report["baseline_comparison"].items():
            if isinstance(val, dict) and "delta" in val:
                print(f"  {key}: {val['delta']:+.0f} (baseline: {val.get('baseline_pass', val.get('baseline_completed', 0))}, "
                      f"current: {val.get('current_pass', val.get('current_completed', 0))})")


if __name__ == "__main__":
    main()
