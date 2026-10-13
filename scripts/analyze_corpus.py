"""Analyze the engineering benchmark corpus and produce a failure taxonomy."""
import json
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "benchmarks" / "engineering_questions.json"

data = json.loads(CORPUS.read_text(encoding="utf-8"))
cases = data["cases"]

print(f"Total cases: {len(cases)}")
print(f"Version: {data.get('version', 'unknown')}")
print()

# Category breakdown
cats = Counter(c.get("category_name", c.get("category", "unknown")) for c in cases)
print("Categories:")
for k, v in cats.most_common():
    print(f"  {k}: {v}")
print()

# Session type breakdown
stypes = Counter(c.get("session_type", "RACE") for c in cases)
print("Session types:")
for k, v in stypes.most_common():
    print(f"  {k}: {v}")
print()

# Expected status breakdown
statuses = Counter()
for c in cases:
    for s in c.get("expected_status", []):
        statuses[s] += 1
print("Expected statuses:")
for k, v in statuses.most_common():
    print(f"  {k}: {v}")
print()

# Limitation cases
lim = sum(1 for c in cases if c.get("limitation_case"))
print(f"Limitation cases: {lim}")
print()

# Replay expected
replay = sum(1 for c in cases if c.get("replay_expected"))
print(f"Replay expected: {replay}")
print()

# Graph trace expected
graph = sum(1 for c in cases if c.get("graph_trace_expected"))
print(f"Graph trace expected: {graph}")
print()

# Evidence rich
er = sum(1 for c in cases if c.get("evidence_rich"))
print(f"Evidence rich: {er}")
print()

# Counterfactual expectations
cf = Counter(c.get("counterfactual_expected", "none") for c in cases)
print("Counterfactual expectations:")
for k, v in cf.most_common():
    print(f"  {k}: {v}")
print()

# Data availability
da = Counter(c.get("data_availability_expectation", "none") for c in cases)
print("Data availability:")
for k, v in da.most_common():
    print(f"  {k}: {v}")
print()

# Question types
qtypes = Counter(c.get("question_type", "unknown") for c in cases)
print("Question types:")
for k, v in qtypes.most_common():
    print(f"  {k}: {v}")
print()

# Seasons covered
seasons = Counter(c.get("season") for c in cases)
print("Seasons:")
for k, v in sorted(seasons.items()):
    print(f"  {k}: {v}")
print()

# Drivers covered
drivers = Counter()
for c in cases:
    drivers[c.get("driver_a", "unknown")] += 1
    if c.get("driver_b"):
        drivers[c["driver_b"]] += 1
print("Top drivers:")
for k, v in drivers.most_common(10):
    print(f"  {k}: {v}")
print()

# Cases with pattern_discovery
pd_cases = [c for c in cases if c.get("pattern_discovery")]
print(f"Pattern discovery cases: {len(pd_cases)}")
for c in pd_cases:
    print(f"  {c['benchmark_id']}: {c.get('pattern_discovery', {}).get('seasons', [])}")
print()

# Cases with memory probes
mp_cases = [c for c in cases if c.get("memory_probe")]
print(f"Memory probe cases: {len(mp_cases)}")
for c in mp_cases:
    print(f"  {c['benchmark_id']}: {c.get('memory_probe', {}).get('kind', 'unknown')}")
print()

# Cases with invalid_input
inv_cases = [c for c in cases if c.get("invalid_input")]
print(f"Invalid input cases: {len(inv_cases)}")
for c in inv_cases:
    print(f"  {c['benchmark_id']}: {c.get('invalid_input', {}).get('field', 'unknown')}")
print()

# Cases with hypotheses_subset
hs_cases = [c for c in cases if c.get("hypotheses_subset")]
print(f"Hypotheses subset cases: {len(hs_cases)}")
for c in hs_cases:
    print(f"  {c['benchmark_id']}: {c.get('hypotheses_subset', [])}")
