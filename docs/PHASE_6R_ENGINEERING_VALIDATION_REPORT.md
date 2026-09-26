# PHASE 6R — ENGINEERING VALIDATION REPORT

Date: 2026-09-27 · Validation executed against the system at baseline `48f0d5d` plus the three 6R fixes described in §27.

## 1. Validation objective

Determine whether RACEWISE can perform real, evidence-driven race-engineering
investigations end-to-end — question → context → hypotheses → evidence plan →
collection → testing → falsification → counterfactual → synthesis →
provenance → graph → memory → replay → comparison — using measured canonical
data only, with honest limitation reporting wherever data does not exist.

## 2. System version

- Baseline commit `48f0d5d` (`feat(racewise): complete engineering product integration`).
- 691 backend tests passing at baseline; legacy investigation flow 5 passed (independent run).
- 31 historical MCP tools (46 total); 34 API routes; 17 frontend TSX modules.
- See `docs/PHASE_6R_BASELINE_AUDIT.md` for the full baseline record.

## 3. Benchmark methodology

- Corpus: `tests/benchmarks/engineering_questions.json` — 54 structural cases
  (35% intentional limitation cases) across categories A–K and eras
  1950/2000/2022/2023/2024/2025. Expected fields describe STRUCTURAL
  requirements (statuses, evidence presence, provenance completeness, replay
  identity, graph integrity); no expected numerical answers exist anywhere in
  the corpus.
- Runner: `tests/benchmarks/run_engineering_benchmark.py` — executes the real
  chain (engine → graph → memory → replay → comparison → API), records
  per-case structural outcomes, computes coverage metrics WITHOUT a composite
  score, and applies the failure taxonomy to any non-pass.
- Results: `data/benchmarks/6r_benchmark_results.json` (machine-readable).
- Golden set: `tests/benchmarks/phase_6r_goldens.json` captured via
  `tests/benchmarks/capture_phase_6r_goldens.py` (12 canonical investigations
  with input/id/output-hash/snapshot-hash/replay/provenance-hash/graph hashes).

## 4. Benchmark corpus

| Category | Cases | Note |
| --- | --- | --- |
| A — Lap performance | 8 | 2 evidence-rich goldens, 2 non-fused-lap limitations, cross-era, unknown-driver |
| B — Stint performance | 6 | incl. 1950 stint limitation, nonexistent stint control |
| C — Race gap | 6 | incl. 1950/2000 historical degradation, 2025 |
| D — Performance regimes | 5 | incl. 1950/2000 limitations |
| E — Cross-race patterns | 5 | discovery + investigation + unknown-pattern + 1950 discovery |
| F — Hypothesis evaluation | 6 | subsets (H1+H6, H5, H4+H6), race-scope, 1950 |
| G — Counterfactual eligibility | 5 | eligible, ineligible×3, budget-zero control |
| H — Investigation synthesis | 4 | full-chain structural validation at 3 scopes + limitation |
| I — Memory | 4 | exact-scope hit, wrong-scope zero, invalidation exclusion, API layer |
| J — Replay | 2 | lap + race scope identity |
| K — Graph | 3 | LAP golden, limitation graph, REGIME22 family |
| Total | 54 | limitation cases: 19 (35.2%) |

## 5–6. Historical and telemetry coverage

Eras exercised: 1950 (historical-only; honest degradation verified), 2000
(middle era; honest degradation), 2022 (regime/stint/wet-affected race), 2023
(telemetry-rich goldens), 2024 (race gap/regimes/cross-season), 2025 (newest
ingested data). Telemetry-rich and telemetry-unavailable sessions both
represented; evidence-rich and evidence-poor cases both represented.

## 7. Investigation validation

54/54 cases executed without implementation failure: 47 STRUCTURAL_PASS +
7 EXECUTED_LIMITATION (honest INSUFFICIENT_EVIDENCE/UNAVAILABLE outcomes the
corpus expected). Every executed investigation returned the full structural
vocabulary: collection status + raw layer statuses + bounded_by, six
hypothesis evaluations with falsification states, falsification gate,
counterfactual candidates/executed, evidence conflicts, synthesis
(established/measured/contradictory/unavailable/unresolved), decision trace,
11-stage lifecycle all COMPLETED, limitations, epistemic boundaries,
provenance, output hash.

## 8. Hypothesis validation

All six canonical hypotheses (H1_corner_speed … H6_drs) evaluated on every
VALID case with aggregate states from the closed vocabulary. EQ-F02 (subset)
confirmed unrequested hypotheses surface as NOT_REQUESTED rather than being
dropped. Distinct states coexist in one matrix (MIXED_EVIDENCE ×3,
NOT_SUPPORTED ×2, INSUFFICIENT_EVIDENCE ×1 on the LAP6 golden) — support and
contradiction never collapse into a bare SUPPORTED (runner assertion
`untestable_preserved` passed on all 54 cases).

## 9. Falsification validation

The falsification gate is present on every VALID investigation. The LAP6
golden carries 6 DIRECT_CONTRADICTION conflicts preserved UNRESOLVED;
the frontend banner states "the evidence conflict is preserved, never resolved
away". Comparison across laps shows RESOLVED_CONTRADICTION transitions only
where the measured evidence actually changed (EQ-J family + browser E2E).

## 10. Residual validation

Residuals appear as first-class evidence rows ("unexplained residual component
(reported, never assigned)" = −0.659 s on the LAP6 golden, state UNRESOLVED)
with their own evidence ids and provenance. No benchmark output assigns a
residual to any hypothesis; the attribution chain reports residuals with an
explicit interpretation ("window means smooth corner-exit differences the
straight-line model cannot see").

## 11. Counterfactual validation

- Eligible case (EQ-G01/G07): LAP_SPEED_PROFILE executed REMOVE_DEFICIT f=0.5
  with baseline/intervention/parameter/model/claim_class=MODELLED/epistemics
  all present and five validation gates PASS (telemetry, alignment,
  intervention, simulator_mapping, baseline_reproduction error 0.0).
- Ineligible cases: 1950 scope → counterfactual candidate reports
  TELEMETRY_UNAVAILABLE with missing_data (never modelled); race-level request
  (EQ-G03) keeps the request unexecuted with reasons; unknown-driver scope
  returns UNAVAILABLE upstream.
- Budget control (EQ-G05): max_counterfactuals=0 recorded in bounded_by;
  nothing executed.
- Modelled results are labeled "model property; not history, not prediction".

## 12. Race-gap validation

Official classified gap and analytical comparable-lap gap remain separate
fields with explicit semantics text ("different quantities … no equality is
implied"). Measured today: 2024 R14 VER/PER official 33.969 s / analytical
7.864 s over 35 comparable laps; NOR/VER official −0.624 s / analytical
+2.49 s over 35 comparable laps (values differ from pre-6R notes because the
canonical store was re-ingested; determinism binds to the current state).
Comparability exclusions are itemized per lap (pit-in/pit-out/deleted).

## 13. Regime validation

2022 R4 VER/PER measured via API: 8 regimes / 54 comparable laps / 49-row
race timeline / hash `e82266ff8ca09e5a`; timeline rows carry per-lap context
transitions (race-control, telemetry, compound, pit) and change points with
GAP_TREND_CHANGE reasons; the browser view renders the same structure.

## 14. Cross-race validation

2022–2025 / max 6 races / VER-PER-derived corpus: 6 recurring patterns /
48 regime signatures / 6-of-6 races / output hash `61dbc841dd137c02`
(matches the pre-6R record for this scope). Pattern ids re-discovered
deterministically by the runner before investigation (EQ-E01/E02); unknown
pattern ids return UNAVAILABLE with available_pattern_count (EQ-E03); 1950
discovery honestly returns UNAVAILABLE (EQ-E04).

## 15. Graph validation

Four graph goldens captured and replayed IDENTICAL: LAP 58/185
(id `b19ae7cd499446a2` family, snapshot hash `4404ee4a608c1108` at capture),
STINT 97/362, RACE_GAP 35/53, REGIME 41/60. Closed node/edge vocabularies
hold (zero out-of-vocabulary types), zero dangling edges, snapshots verify,
graph replay IDENTICAL. The 1950 limitation case produces either no graph
with a reason or only real-output-backed nodes (EQ-K02 pass).

## 16. Provenance validation

Every VALID investigation: provider, source_tables, method,
analytical_chain, investigation_version present and non-empty (54/54).
Every established fact and measured finding references an existing evidence
ledger id (0 dangling across the corpus). Every synthesis statement resolves
through decision_trace_refs to real decision-trace entries. Evidence rows
carry source phase/tool/hash/scope. Counterfactuals carry baseline,
intervention, parameter, model, assumptions and validation gates. Graph edges
carry provenance of their imported relationship.

## 17–18. Memory, replay, comparison validation

- Memory: 7 items derived from the LAP6 golden; exact-scope retrieval returns
  exactly those 7; wrong-scope retrieval returns exactly 0 (no leakage);
  invalidated items are excluded by default and included only when explicitly
  requested; the API layer returns matching items with policy text intact.
- Replay: 11 replay executions across the corpus and goldens, all IDENTICAL
  (snapshot hash == replay hash; includes `a7a0446765a05e4f`).
- Comparison: lap 6 vs lap 11 PARTIALLY_COMPARABLE (differing: lap_number)
  with synthesis transition MIXED_EVIDENCE → SUPPORTED_BY_AVAILABLE_EVIDENCE
  (MORE_SUPPORTED); per-hypothesis deltas are descriptive (STATE_CHANGED /
  unchanged), never ranked.

## 19. API validation

20 probes, all pass: 15×200 with real data (health, sessions, telemetry,
attribution, fusion, stint, counterfactual, envelope, race-gap ×2, regimes,
patterns, search, investigation, graph, memory), 2×422 on invalid vocabulary /
out-of-range season (expected contract), 1×200+UNAVAILABLE on unknown driver,
1×404 on missing route. Latency p50 0.575 s / p95 6.29 s / max 16.0 s.

## 20. Frontend validation (E2E, real browser)

All 17 views exercised with real interactions at 1440×900: Investigation
workspace (matrix, ledger filters, decision trace, provenance drawer, evidence
details → trace-to-source → BACK navigation, replay IDENTICAL in-place,
compare lap B, memory retrieval), Lap Comparison (PASS 2.084 s / 20 windows
with assumptions), Lap Attribution (0.185 s delta, sector sum, residual),
Evidence Fusion (formal verdicts with basis evidence), Stint Analysis
(trend 0.1865 s/stint), Race Gap (official vs analytical separate),
Counterfactuals (5 gates PASS), Performance Envelope (33.0 km/h band,
monotonic sensitivity), Performance Regimes (8 regimes timeline), Cross-Race
Patterns (6 patterns + deep links), Pattern Evidence (fixed workflow, real
evidence matrix), Graph (58 nodes/185 edges), Memory (7 items), Replay
(IDENTICAL), Compare (dimension deltas), Catalog (capability-derived), plus
error states: unknown driver → visible UNAVAILABLE with reason and "nothing is
broadened silently"; invalid question type → visible 422 message. No blank
states, no dead controls, no fabricated charts.

## 21. Determinism

Same-process: 3× repeated execution on 8 canonical scopes — byte-identical
output hashes. Cross-process: PYTHONHASHSEED=3 vs PYTHONHASHSEED=29
subprocess runs on lap- and race-scope cases — identical hashes and
investigation ids. Replay verdicts IDENTICAL on all 11 executions. MCP path
shares the same deterministic engine (31 historical tools exercised by the
existing test suite; no separate MCP implementation to diverge).

## 22. Performance (measured, p50/p95/max)

| Operation | p50 | p95 | max |
| --- | --- | --- | --- |
| Benchmark investigation (54 cases) | 1.14 s | 17.66 s | 59.06 s |
| API probes (20 routes) | 0.58 s | 6.29 s | 16.00 s |

Slowest operations: cross-race patterns (~14–16 s at 4-season scope) and
pattern-evidence (~16 s incl. re-discovery) — assessed EXPECTED_ANALYTICAL_COST
(bounded enumeration × regime segmentation × structural matching); frontend
build 5.9–10.4 s; graph build ~0.7–0.9 s; replay sub-second on lap scope.

## 23. Storage

Before/after full benchmark execution (54 investigations + replays + graph
builds + memory derivations + comparisons): zero row growth across all 15
canonical tables (canonical_telemetry, canonical_results, canonical_lap_times,
…). Derived-on-read behavior confirmed intact.

## 24. Security

Static scan over src/, tests/benchmarks/, apps/web/src: 0 eval/exec, 0 shell
invocation, 0 unsafe HTML, 0 secret/API-key exposure; 4 dynamic-SQL
detections all SAFE (3 parameterized/identifier-allowlisted upstream, 1
quote-doubling sanitized in the 6R runner). Existing security tests pass
within the full regression. MCP boundaries untouched.

## 25. No-fabrication scan

0 unsafe occurrences across production and frontend code. 29 occurrences of
the word "fabricated" all classified as anti-fabrication guard documentation
("never a fabricated …", "nothing is fabricated"). No benchmark fixtures are
consumed by production code; the corpus file is referenced only by the 6R
runner and docs.

## 26. Failure taxonomy

Final state: zero unexpected failures. Historical triage during the phase:
18 initial non-passes → 16 corpus/runner vocabulary corrections (benchmark
side), 1 API_GAP fixed (pattern-evidence 500), 1 FRONTEND_GAP fixed
(patterns→evidence workflow). See `docs/PHASE_6R_GAP_ANALYSIS.md`.

## 27. Fixed defects

1. **pattern-evidence 500 (API_GAP)** — missing local `get_catalog_api`
   import in the default-pair branch of
   `/api/catalog/performance-pattern-evidence`. One-line fix in
   `src/racewise/api/app.py`; endpoint now returns 200 with honest status.
2. **Pattern Evidence deep-link + scope binding (FRONTEND_GAP)** —
   `PatternEvidenceView` accepts `#/patternevidence?pattern_id=&driver_a=&driver_b=&seasons=`
   and binds the corpus scope into the request; `PerformancePatternView`
   exposes full-fidelity "Investigate evidence →" links. tsc + build clean.

## 28. Remaining limitations

- Fused lap evidence limited to 6D probe laps (honest INSUFFICIENT elsewhere).
- 6N engine supports session_type=RACE only.
- Memory is exact-scope matching only (by design; zero leakage verified).
- Catalog investigation graph is scope-based (no investigation-id mode).
- Cross-race patterns/pattern-evidence cost 14–16 s at wide scopes.
- Driver identity is slug-based throughout the deterministic chain.
- Canonical-data evolution changes measured values (documented in gap analysis §D); hashes bind to the current store state.

## 29. Genuine missing capabilities

See `docs/NEXT_CAPABILITY_GAPS.md` (4 items, none correctness defects, none
implemented automatically).

## 30. Final readiness

All major workflows work end-to-end; determinism preserved (same-process,
cross-process, PYTHONHASHSEED 3/29, replay 11/11 IDENTICAL); provenance
complete (54/54 investigations, 0 dangling references); frontend integration
complete (17/17 views + error states verified in a real browser); no critical
security defects; remaining failures are understood, documented limitations.

**Status: READY_WITH_DOCUMENTED_LIMITATIONS**

The qualifier reflects documented, understood data/contract limitations
(probe-lap fusion coverage, RACE-only sessions, exact-scope memory,
scope-based graph endpoint) — not defects. Every limitation is reported
honestly by the system itself at runtime.
