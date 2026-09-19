# Golden Investigations — Verified Results

Three real RACEWISE investigations run against the canonical store (F1DB v2026.14.0) on 2026-09-19 via `src/racewise/data/historical/golden_investigations.py` (`run_all_golden_investigations()`). Raw outputs are persisted at `data/ingestion_state/golden_results.json`.

## Golden #1 — 1950 British GP (deep historical identity)

**Status: PASS** (hash `1487764bf78a3c38`)

- Race, season, circuit, drivers, constructors all resolve; 21 classified entries.
- Provenance present on every row (provider, source id, source version).
- Modern evidence correctly declared UNAVAILABLE: pit stops, stints, weather, race control, telemetry.
- Cross-provider check vs Jolpica: 41 MATCH / 51 NOT_AVAILABLE / 2 MISMATCH (preserved, see `CROSS_PROVIDER_VALIDATION.md`).

## Golden #2 — 2000 Australian GP (middle era)

**Status: PASS** (hash `43434c839bd05315`)

- 22 results, 22 grid/qualifying rows, 23 pit stops, 21 fastest-lap facts.
- Explicitly distinguishes AVAILABLE (results/grid/pits/fastest laps) from UNAVAILABLE (tyre compounds, weather, telemetry).
- No synthetic stints or compounds invented.

## Golden #3 — 2023 Bahrain GP (deep modern era)

**Status: PASS** (hash `b56bc01979f048e2`)

- Full pipeline: QUESTION → HYPOTHESES → EVIDENCE → FALSIFICATION → COUNTERFACTUAL → CONCLUSION → PROVENANCE.
- Canonical evidence: 20 results, 20 qualifying rows, 50 pit stops, 20 fastest-lap facts.
- FastF1 context (telemetry-shaped data) loaded from the real local cache where available; anything FastF1 cannot provide is declared DATA_UNAVAILABLE, never faked.
- **Counterfactual validated**: deterministic `simulate_pit_timing` executed by RACEWISE code; scenario, inputs, model version, output and assumptions persisted in the investigation payload. The agent did not invent the result.

## Replay / determinism

Each investigation payload (excluding timestamps) hashes deterministically. A fresh subprocess (simulated application restart) recomputed all four hashes:

```
golden_1950_british_gp        1487764bf78a3c38  REPLAY MATCH
golden_2000_australian_gp     43434c839bd05315  REPLAY MATCH
golden_2023_bahrain_gp        b56bc01979f048e2  REPLAY MATCH
cross_provider_1950_british   276591d5d8c104bd  REPLAY MATCH
REPLAY: PASS
```

## How to run

```bash
python -c "import sys; sys.path.insert(0,'src'); \
from racewise.data.historical.golden_investigations import run_all_golden_investigations; \
import json; print(json.dumps(run_all_golden_investigations(), indent=2, default=str))"
```

Integration tests `tests/integration/test_golden_investigations.py` guard these properties (skipped with a clear message if the canonical DB has not been ingested).
