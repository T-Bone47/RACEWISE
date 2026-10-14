"""Categorize all corpus failures by root-cause pattern."""
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.question_engine.benchmark import measure, CASES

queries = CanonicalQueries()
result = measure(queries)

# Bucket failures by the first reason's shape
def bucket(reason: str) -> str:
    r = reason.lower()
    if "status" in r and "unsupported" in r:
        return "STATUS_UNSUPPORTED (intake rejected phrasing)"
    if "status" in r and "context_unresolved" in r:
        return "STATUS_CONTEXT_UNRESOLVED (scope not resolved)"
    if "intents" in r:
        return "INTENT_MISS (no matching intent family)"
    if "capabilities missing" in r:
        return "CAPABILITY_MISS (planner didn't select)"
    if "subquestions" in r:
        return "SUBQUESTION_SHORT (decomposition too few)"
    if "season" in r or "round" in r or "driver" in r:
        return "ENTITY_MISMATCH (resolved wrong entity)"
    return f"OTHER: {reason[:50]}"

counter: Counter = Counter()
examples: dict[str, list] = {}
for failure in result["failures"]:
    # a case can have multiple reasons; bucket each
    for reason in failure["reasons"]:
        b = bucket(reason)
        counter[b] += 1
        examples.setdefault(b, []).append(
            (failure["case_id"], failure["question"][:55], reason[:70])
        )

print(f"Total failing cases: {result['failed']}")
print(f"Total failure reasons: {sum(counter.values())}")
print()
print("Failure buckets (by count):")
for bucket_name, count in counter.most_common():
    print(f"  {count:3d}  {bucket_name}")
print()
print("=" * 70)
for bucket_name, count in counter.most_common():
    print(f"\n### {bucket_name} ({count} reasons)")
    seen = set()
    for case_id, question, reason in examples[bucket_name]:
        key = (question[:30], reason[:40])
        if key in seen:
            continue
        seen.add(key)
        print(f"  {case_id} {question}")
        print(f"      -> {reason}")
