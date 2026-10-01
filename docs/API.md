# RACEWISE API Reference

**Base URL:** `http://localhost:8000` (FastAPI app: `src/racewise/api/app.py`)
**Interactive docs:** `http://localhost:8000/docs` (OpenAPI)

## Authentication

None. The API is read-only over the canonical store and the deterministic
analytical chain. No secrets are exposed; no write operations exist on the
catalog chain.

## Endpoint families

### Health
- `GET /api/health` — service, version, model provider status.

### Canonical catalog (Phase 6B)
- `GET /api/catalog/sessions` — paginated, filterable session catalog (`season`,
  `session_type`, `country`, `circuit`, `provider`, `availability`,
  `capability`, `search`). Availability flags are record-count derived only.
- `GET /api/catalog/sessions/{season}/{round}/{session_type}` — session
  identity, providers, per-facet capability counts, provenance. 404 when not
  in the canonical catalog.
- `GET /api/catalog/search?q=&result_type=&season=&limit=` — deterministic
  typed search (`RACE`, `DRIVER`, `HYPOTHESIS`, `INVESTIGATION`, `EVIDENCE`,
  `PATTERN`, `MEMORY`).

### Deterministic analytics (per season/round, RACE-scoped telemetry policy)
- `GET /api/catalog/telemetry-comparison/{season}/{round}` — bounded
  per-window comparison (`driver_a`, `driver_b`, `lap`).
- `GET /api/catalog/attribution/{season}/{round}` — Phase 6E lap-loss
  attribution with residual and falsification.
- `GET /api/catalog/evidence-fusion/{season}/{round}` — Phase 6F multi-source
  evidence fusion with formal per-hypothesis verdicts.
- `GET /api/catalog/stint-evidence/{season}/{round}` — Phase 6G stint trend +
  hypothesis evolution (`stint` optional; deterministic default).
- `GET /api/catalog/race-gap/{season}/{round}` — Phase 6H race-gap
  decomposition.
- `GET /api/catalog/performance-regimes/{season}/{round}` — Phase 6K OLS slope
  segmentation (`max_regimes`, `start_lap`, `end_lap`).
- `GET /api/catalog/performance-patterns` — Phase 6L cross-race structural
  patterns (`driver_a`, `driver_b`, `seasons`, `max_races`, `max_patterns`).
- `GET /api/catalog/performance-pattern-evidence` — Phase 6M cross-race
  hypothesis/evidence investigation of one pattern (`pattern_id` required).

### Phase 6I/6J counterfactual + envelope
- `GET /api/catalog/counterfactual/{season}/{round}` — validated
  `REMOVE_DEFICIT` speed-profile counterfactual (`driver`, `reference_driver`,
  `lap`, `fraction` ∈ [0, 1]). Statuses: `VALID`, `INSUFFICIENT_EVIDENCE`,
  `UNAVAILABLE`, `UNSUPPORTED`, `INVALID`.
  - `include_profile=true` (opt-in) additionally returns `profile_samples`:
    a bounded (cap 192), evenly spaced, deterministic decimation of the
    aligned speed profiles (`t_s`, `target_kmh`, `reference_kmh`,
    `counterfactual_kmh`) for display. Default **off** keeps the canonical
    payload and its `output_hash` byte-identical to previous versions.
- `GET /api/catalog/performance-envelope/{season}/{round}` — Phase 6J measured
  envelope + bounded scenario sweep + sensitivity classification
  (`scenario_type` ∈ `OBSERVED`, `DEFICIT_REDUCTION`, `REFERENCE_BLEND`,
  `ENVELOPE_LOWER_BOUND`, `ENVELOPE_UPPER_BOUND`; `parameter`, `stint`).

### Session context (Stitch-integration extension)
- `GET /api/catalog/session-context/{season}/{round}` — real measured context
  for the investigation context strip: `stints_by_driver` (compound + lap
  windows), `laps_by_driver` (per-lap `position`, `time_s`, `compound`,
  `tyre_life` for up to 4 requested `drivers`), `weather` summary (measured
  values or an honest `UNAVAILABLE`), and `telemetry` coverage facts
  (`covered_laps`, `analysis_grid_s` = 0.25, bounded policy). `session_type`
  ∈ `RACE`, `QUALIFYING` (422 otherwise). Composed from existing canonical
  queries only — no derivation, no interpolation.

### Phase 6N/6O/6P engineering investigation chain
All take the structured scope params: `question_type`, `driver_a`, `driver_b`,
`season`, `round`, `lap_number`, `stint_number`, `pattern_id`, `hypotheses`,
`session_type`.
- `GET /api/catalog/engineering-investigation` — full 6N payload:
  evidence plan, evidence ledger, hypothesis evaluations (canonical states),
  falsification gate, counterfactual candidates/executed, evidence conflicts,
  synthesis, decision trace, lifecycle, snapshot, epistemic boundaries,
  provenance, output hash.
- `GET /api/catalog/engineering-investigation/replay` — 6O deterministic
  replay: rebuilds the snapshot, re-runs the engine, compares hashes;
  statuses `IDENTICAL`, `DIFFERENT_*`, `INVALID_SNAPSHOT` with structured
  differences.
- `GET /api/catalog/engineering-investigation/compare` — dimension-wise
  comparison of two scopes (`a_*` / `b_*` params).
- `GET /api/catalog/engineering-memory` — exact-scope memory retrieval
  (`include_related` adds structural related items). Derived on read.
- `GET /api/catalog/investigation-graph` (+ `/path`, `/evidence`,
  `/hypothesis`) — the Phase 6P engineering investigation graph: typed
  nodes/edges, provenance-backed, derived on read. Never a causal graph.

### Legacy investigation engine (LLM/deterministic MVP chain)
- `POST /api/investigations` — create (question, year, event, driver).
- `GET /api/investigations` / `GET /api/investigations/{id}` /
  `GET /api/investigations/{id}/stream` (SSE) / `export` / `DELETE`.
- `POST /api/investigations/{id}/counterfactual` — pit-timing counterfactual
  (explicitly labelled COUNTERFACTUAL estimate).
- `POST /api/investigations/{id}/replay` — event-log re-execution + hash verify.
- `GET /api/investigations/{inv_id}/evidence-graph` (+ POST relationship).

### Autonomous investigations (Phase 6T)
- `POST /api/investigations/autonomous` — question → deterministic run record
  (`run_id`, stage ledger, decision trace, engine result ref). 422 for
  invalid/unsupported questions, 409 for unresolved context.
- `GET /api/investigations/autonomous/runs` — persisted runs, newest first.
- `GET /api/investigations/autonomous/{run_id}` — one full record.
- `POST /api/investigations/autonomous/{run_id}/continue` — enlarged budget re-run.
- `POST /api/investigations/autonomous/{run_id}/replay` — deterministic replay.
- `GET /api/investigations/autonomous/{run_id}/stream` — SSE stage events.

### Legacy session catalog (FastF1-backed)
- `GET /api/sessions`, `GET /api/sessions/{session_key}/drivers`,
  `POST /api/sessions/sync`.

## Error responses

- `404` — session/investigation not found in the canonical catalog. Never a
  silent fallback.
- `422` — out-of-bounds or unknown parameters; the closed vocabulary list is
  returned in `detail`. Bounds are rejected, never clamped.

## Honest-state contract

`UNAVAILABLE`, `INSUFFICIENT_EVIDENCE`, `NOT_TESTABLE`, `NOT_REQUESTED`,
`UNSUPPORTED` are first-class results. The UI must render them; it must never
substitute a synthetic series, an implied zero, or a broadened scope.

## Rate limiting

None (local research deployment).
