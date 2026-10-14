"""Measure the question-engine corpus pass rate (230 questions)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.question_engine.benchmark import measure


def main() -> None:
    queries = CanonicalQueries()
    result = measure(queries)
    print(f"Corpus: {result['cases']} cases")
    print(f"Passed: {result['passed']}")
    print(f"Failed: {result['failed']}")
    print(f"Pass rate: {result['pass_rate'] * 100:.1f}%")
    print()
    print("By category (worst first):")
    for name, bucket in sorted(
        result["by_category"].items(),
        key=lambda kv: kv[1]["passed"] / max(1, kv[1]["total"]),
    ):
        total = bucket["total"]
        passed = bucket["passed"]
        pct = 100 * passed / total if total else 0
        print(f"  {name:16s} {passed:3d}/{total:3d} ({pct:5.1f}%)")
    print()
    print("Failure details:")
    for failure in result["failures"]:
        reasons = "; ".join(failure["reasons"])
        print(f"  {failure['case_id']} [{failure['question'][:60]}]")
        print(f"      -> {reasons}")


if __name__ == "__main__":
    main()
