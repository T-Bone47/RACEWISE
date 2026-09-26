# RACEWISE — PRODUCT INTEGRATION COMPLETION REPORT

## 1. Executive summary

RACEWISE's frontend now presents as one engineering product rather than a
sequence of internal development phases. All user-facing navigation,
headings, palette commands, and status text use capability-oriented
engineering terminology; internal phase identifiers (6E–6Q) remain only in
source comments, provenance metadata, tests, and documentation where they
belong. Every implemented backend analytical capability is reachable from
the UI and was exercised end-to-end in a live browser against the canonical
store. Two real product bugs surfaced by the sweep were fixed
(`EvidenceFusionView` crash on rendering hypothesis evidence lists — the
field is `untestable`, not `not_tested_by`; and a missing loading state on
the Regimes view). No analytical logic changed; no capability was removed;
no data was fabricated.

## 2. Navigation: before / after

| before (internal labels) | after (product concepts) |
|---|---|
| 6E Attribution | Lap Attribution |
| 6F Evidence Fusion | Evidence Fusion |
| 6G Stint Evidence | Stint Analysis |
| 6H Race Gap | Race Gap |
| 6I Counterfactual | Counterfactuals |
| 6J Envelope | Performance Envelope |
| 6K Regimes | Performance Regimes |
| 6L Patterns | Cross-Race Patterns |
| 6M Pattern Evidence | Pattern Evidence |
| "Analytical chain" group | "Engineering" group |
| CHAIN 6E–6P READY (status bar) | DETERMINISTIC CHAIN READY |
| PHASE 6Q WORKSPACE (status bar) | RACEWISE ENGINEERING WORKSPACE |
| "Open 6I counterfactual simulator" (palette) | "Open counterfactual simulator" |

Command-center hero, shortcut tiles, evidence-plan line, and all panel
headings were similarly cleaned. The final repo-wide sweep for
`6E|6F|…|6Q|Phase 6` in rendered TSX returns only code comments and the
`cross_check_6e` backend field name (an API contract key, rendered with
product language around it).

## 3. Frontend routes (all verified live)

`#/command` (landing: real recents, live catalog status, launcher) ·
`#/investigate` (full workspace: matrix, ledger, decision trace, graph,
counterfactuals, synthesis, replay, compare, memory) · `#/graph` ·
`#/replay` · `#/compare` · `#/memory` · `#/catalog` · `#/telemetry`
(Lap Comparison) · `#/attribution` · `#/fusion` · `#/stint` · `#/racegap` ·
`#/counterfactual` · `#/envelope` · `#/regime` · `#/patterns` ·
`#/patternevidence`. Deep links carry scope params and survive refresh
(hash routing).

## 4. Capability matrix

| capability | backend | API | MCP | frontend | status |
|---|---|---|---|---|---|
| Catalog / session detail | ✓ | /api/catalog/sessions | ✓ | CatalogExplorer | WIRED |
| Lap comparison (telemetry) | ✓ | /api/catalog/telemetry-comparison | ✓ | TelemetryView | WIRED (verified: 2.084s loss, 20 windows, provenance) |
| Lap attribution | ✓ | /api/catalog/attribution | ✓ | AttributionView | WIRED (verified: sector sums to 0.185s delta) |
| Evidence fusion | ✓ | /api/catalog/evidence-fusion | ✓ | EvidenceFusionView | WIRED (crash fixed) |
| Stint analysis | ✓ | /api/catalog/stint-evidence | ✓ | StintEvidenceView | WIRED (verified: trend 0.1865 s/s) |
| Race gap | ✓ | /api/catalog/race-gap | ✓ | RaceGapView | WIRED (official vs analytical gap separated) |
| Counterfactual | ✓ | /api/catalog/counterfactual | ✓ | CounterfactualView | WIRED (REMOVE_DEFICIT verified) |
| Performance envelope | ✓ | /api/catalog/performance-envelope | ✓ | EnvelopeView | WIRED (reproduction error 0 s) |
| Performance regimes | ✓ | /api/catalog/performance-regimes | ✓ | RegimeView | WIRED (8 regimes, 220-row timeline) |
| Cross-race patterns | ✓ | /api/catalog/performance-patterns | ✓ | PatternView | WIRED (6 patterns, hash 61dbc841dd137c02) |
| Pattern evidence | ✓ | /api/catalog/performance-pattern-evidence | ✓ | PatternEvidenceView | WIRED |
| Investigation (6N engine) | ✓ | /api/catalog/engineering-investigation | ✓ | InvestigationView | WIRED (fcc1bf694daada8e) |
| Replay | ✓ | …/replay | ✓ | ReplayPanel | WIRED (IDENTICAL) |
| Comparison | ✓ | …/compare | ✓ | ComparePanel | WIRED (COMPARABLE) |
| Engineering memory | ✓ | /api/catalog/engineering-memory | ✓ | MemoryPanel | WIRED (7 items) |
| Engineering graph | ✓ | /api/catalog/investigation-graph[/…] | ✓ | GraphPanel | WIRED (58 nodes · 185 edges) |
| Global search | ✓ | /api/catalog/search | — | Command palette | WIRED |

Nothing implemented in the backend lacked a frontend surface; nothing in
the UI calls an endpoint the backend does not expose.

## 5. Bugs found & fixed during integration

1. **EvidenceFusionView crash** (white screen on result render): the view
   read `h.not_tested_by` while the backend contract field is `untestable`.
   Fixed to the real contract with null-safe rendering.
2. **Regimes view silent run**: no in-flight indicator while a 10–20 s
   segmentation ran. Added a context-specific loading line
   ("Segmenting the comparable-lap gap series into regimes…").

## 6. Workflow verification (live browser, canonical data)

- Lap Comparison: 2023 R1 VER/PER lap 6 → PASS, 2.084 s across 20 windows,
  window table + bars + assumptions + provenance line.
- Lap Attribution: 2023 R1 → sector deltas measured, sum equals observed
  lap delta (0.185 s); INSUFFICIENT_EVIDENCE path verified on a session
  without comparable laps (honest empty state, no fabrication).
- Evidence Fusion: 6 formal hypothesis verdicts; supporting evidence lists
  render from real sector/region/speed IDs.
- Stint: 2023 R1 stint 2 → per-lap deltas, trend 0.1865 s/s, context chips.
- Race Gap: 2024 R14 NOR/VER → official classified gap (0.895 s) shown
  separately from analytical comparable-lap gap with explicit distinction.
- Counterfactual: REMOVE_DEFICIT fraction 0.5, modelled-delta framing,
  attribution cross-check line.
- Envelope: anchor lap 6, band 33.0 km/h, baseline reproduction error 0 s.
- Regimes: 2022 R4 → 8 regimes / 42 comparable laps, timeline with race
  control + weather transitions and change points.
- Patterns: 6 recurring patterns across 6 races with output hash.
- Investigation → graph (58 nodes · 185 edges) → memory (7 scope-bound
  items) → replay (IDENTICAL) → compare (COMPARABLE).
- Catalog: 25 rows/page with availability icons; investigate handoff gated
  on classification availability.

## 7. Loading / empty / error / unavailable states

Every analytical view has a structured error surface (`catalog-error`),
an honest empty state (`catalog-empty`, e.g. INSUFFICIENT_EVIDENCE with the
backend's reason), and in-flight labels. The investigation workspace uses
layout-mirroring skeletons. No view renders a blank screen on empty or
failure — verified across telemetry-poor and telemetry-rich sessions.

## 8. Determinism, contracts, security

- Repeat of the representative investigation reproduced investigation id
  `fcc1bf694daada8e` (content-addressed) and identical outputs.
- No API contract changed; the only backend-adjacent edit in this task was
  none — all changes are frontend-only.
- Frontend remains free of eval/innerHTML/secrets; data comes exclusively
  from the API layer; MCP boundary untouched.

## 9. Test results

- Backend regression (full suite, excluding the other thread's legacy-flow
  file per established precedent): see commit report — run before commit.
- Legacy-flow test: run independently (5 passed).
- Frontend: `tsc --noEmit` clean, `npm run build` clean, oxlint 0 errors
  (2 pre-existing warnings in pre-existing code).
- `npm test`: no test runner is configured in apps/web (frontend quality is
  guarded by tsc strict + oxlint + live E2E) — documented as a limitation.

## 10. Known limitations (honest)

- Chart rendering in Lap Comparison is bar/table based (backend returns
  windowed aggregates, not raw traces; no invented traces are drawn).
- Search covers races/drivers/hypotheses/pattern-ids/16-hex ids; evidence
  free-text search lives in the ledger filter, not global search.
- Frontend unit tests (npm test) are not configured; coverage is via
  strict types, lint, and manual E2E.
- UNION ALPHA agent surface is not part of the UI; the deterministic
  engine is the only numerical authority shown.
