"""RACEWISE benchmark harness: fixed questions, honest measured scoring.

Runs deterministic investigations end-to-end through the API layer and
records actual results to benchmark_results.json. No manufactured scores.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient

from racewise.api.app import app

BENCHMARK_QUESTIONS = [
    # Core categories (original 8)
    {"id": "B01", "category": "tyre_degradation", "driver": "VER", "question": "Why did VER lose pace in stint 2?"},
    {"id": "B02", "category": "traffic", "driver": "LEC", "question": "Did traffic cost LEC pace in the opening stint?"},
    {"id": "B03", "category": "strategy", "driver": "VER", "question": "Would an earlier pit stop have changed VER's race outcome?"},
    {"id": "B04", "category": "driver_comparison", "driver": "HAM", "question": "Was HAM genuinely slower than VER on comparable stints?"},
    {"id": "B05", "category": "pace_anomaly", "driver": "ALB", "question": "Did ALB show anomalous laps in the first stint?"},
    {"id": "B06", "category": "pit_timing", "driver": "PER", "question": "How much time did PER lose in pit cycles?"},
    {"id": "B07", "category": "weather", "driver": "SAI", "question": "Did weather changes affect SAI's second stint?"},
    {"id": "B08", "category": "counterfactual", "driver": "ALO", "question": "What if ALO had pitted five laps later?"},

    # Adversarial questions (≥5) - challenge premises, test falsification
    {"id": "B09", "category": "adversarial", "driver": "VER", "question": "Was tyre degradation actually the dominant explanation for VER's pace drop, or did traffic play a larger role?"},
    {"id": "B10", "category": "adversarial", "driver": "HAM", "question": "Is the claim that HAM was slower than VER supported when controlling for tyre age and compound?"},
    {"id": "B11", "category": "adversarial", "driver": "PER", "question": "Did PER's poor result stem from car pace or strategy execution errors?"},
    {"id": "B12", "category": "adversarial", "driver": "SAI", "question": "Was SAI's second stint pace loss due to degradation or track evolution affecting all drivers?"},
    {"id": "B13", "category": "adversarial", "driver": "ALO", "question": "Can ALO's race be explained by a single factor, or were multiple compounding issues present?"},

    # Counterfactual questions (≥5) - require deterministic simulator
    {"id": "B14", "category": "counterfactual", "driver": "VER", "question": "What if VER had pitted 5 laps earlier in stint 2?"},
    {"id": "B15", "category": "counterfactual", "driver": "LEC", "question": "What if LEC had used HARD tyres instead of MEDIUM for stint 2?"},
    {"id": "B16", "category": "counterfactual", "driver": "HAM", "question": "What if HAM had a two-stop strategy instead of one-stop?"},
    {"id": "B17", "category": "counterfactual", "driver": "ALO", "question": "What if ALO had pitted under the virtual safety car?"},
    {"id": "B18", "category": "counterfactual", "driver": "PER", "question": "What if PER had started on SOFT instead of MEDIUM compound?"},

    # Comparative driver questions (≥5) - multi-driver analysis
    {"id": "B19", "category": "driver_comparison", "driver": "VER", "question": "Compare VER vs PER vs ALO: who had the best race pace in clean air?"},
    {"id": "B20", "category": "driver_comparison", "driver": "HAM", "question": "Compare HAM vs RUS: was the teammate gap explained by strategy or pace?"},
    {"id": "B21", "category": "driver_comparison", "driver": "LEC", "question": "Compare LEC vs SAI: did tyre management differ between Ferrari drivers?"},
    {"id": "B22", "category": "driver_comparison", "driver": "NOR", "question": "Compare NOR vs PIA: rookie vs experienced driver race craft in traffic?"},
    {"id": "B23", "category": "driver_comparison", "driver": "GAS", "question": "Compare GAS vs OCO: Alpine vs AlphaTauri tyre degradation profile?"},
]


def run_benchmark() -> list[dict]:
    client = TestClient(app)
    results: list[dict] = []
    for q in BENCHMARK_QUESTIONS:
        start = time.perf_counter()
        create = client.post(
            "/api/investigations",
            json={"question": q["question"], "year": 2023, "event": "Bahrain", "driver": q["driver"]},
        )
        if create.status_code != 200:
            results.append({"id": q["id"], "category": q["category"], "status": "CREATE_FAILED"})
            continue
        inv_id = create.json()["investigation_id"]
        with client.stream("GET", f"/api/investigations/{inv_id}/stream") as stream:
            for _ in stream.iter_lines():
                pass
        latency_s = round(time.perf_counter() - start, 2)
        detail = client.get(f"/api/investigations/{inv_id}").json()
        results.append(
            {
                "id": q["id"],
                "category": q["category"],
                "driver": q["driver"],
                "state": detail["state"],
                "hypotheses": len(detail["hypotheses"]),
                "evidence": len(detail["evidence"]),
                "falsification_attempted": any(ev["contradicts"] for ev in detail["evidence"]),
                "counterfactual": len(detail["counterfactuals"]) > 0,
                "tools_executed": len(detail["tool_executions"]),
                "all_tools_completed": all(te["status"] == "completed" for te in detail["tool_executions"]),
                "has_conclusion": detail["conclusion"] is not None,
                "latency_s": latency_s,
            }
        )
    return results


def main() -> None:
    results = run_benchmark()
    completed = sum(1 for r in results if r.get("state") == "COMPLETED")
    falsified = sum(1 for r in results if r.get("falsification_attempted"))
    counterfactuals = sum(1 for r in results if r.get("counterfactual"))
    summary = {
        "n_questions": len(results),
        "completed": completed,
        "completion_rate": round(completed / len(results), 3) if results else 0.0,
        "falsification_rate": round(falsified / len(results), 3) if results else 0.0,
        "counterfactual_rate": round(counterfactuals / len(results), 3) if results else 0.0,
        "note": "Deterministic rules-based plan; LLM-dependent dimensions (tool-selection adaptivity, claim faithfulness) not scored without a configured model.",
    }
    output = {"summary": summary, "results": results}
    out_path = ROOT / "benchmark_results.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    for r in results:
        print(r)


if __name__ == "__main__":
    main()
