# STITCH ↔ RACEWISE Feature Reconciliation Matrix

**Version:** 2.0 — final integration contract (statuses updated at completion)
**Stitch source of truth:** `stitch_racewise_telemetry_investigation_platform/` (DESIGN.md + 6 screens)
**RACEWISE source of truth:** `src/racewise/` (deterministic engine + canonical store), `apps/web/` (React/Vite frontend)
**Behavioral source of truth:** `tests/` (backend: 801 tests) + `apps/web/src/*.test.ts(x)` (frontend: 70 tests)

## Governing rules

1. **Stitch = visual/UX truth. RACEWISE = functional/data truth. Existing tests = behavioral truth.**
2. No fabricated confidence values (`94.2%`, `P=0.98`, `99.4%`, `FALSIFIED (99%)`, `CONFIRMED (87%)`, `PROBABILISTIC (62%)`) appear in the product — a fabrication-guard test suite enforces this over every production source file.
3. No 100 Hz claims. Measured truth: native provider telemetry is ~3.7 Hz (≈0.16–0.40 s inter-sample), resampled by the engine onto a **0.25 s analysis grid** (`loss_attribution.ALPHA_RESAMPLE`). The UI says exactly that.
4. No causal graph. The real artifact is the Phase 6P **engineering investigation graph** (typed nodes/edges, provenance-backed, derived on read).
5. Hypothesis states remain the canonical 8: `SUPPORTED`, `PARTIALLY_SUPPORTED`, `NOT_SUPPORTED`, `CONTRADICTED`, `NOT_TESTABLE`, `INSUFFICIENT_EVIDENCE`, `MIXED_EVIDENCE`, `NOT_REQUESTED`. Never invented, never silently converted.
6. Residuals stay `UNRESOLVED` — never assigned to a mechanism without evidence.
7. Counterfactual values are always labelled **MODELLED — NOT HISTORICAL**.
8. Every visible control calls a real API or renders an honest unavailable state. No dead buttons, no dead routes.

## Screens inspected (all files in the ZIP)

| Stitch screen | Files |
|---|---|
| Active Investigation Workspace (v1) | `active_investigation_workspace/code.html` |
| Active Investigation Workspace (v2) | `active_investigation_workspace_v2/code.html` |
| Active Investigation Workspace (v3, flagship) | `active_investigation_workspace_v3/code.html` |
| Engineering Command Center | `engineering_command_center/code.html` |
| Falsification Matrix | `falsification_matrix/code.html` |
| Counterfactual Lab | `counterfactual_lab/code.html` |
| Design system | `telemetry_investigation_workbench/DESIGN.md` |

## Status legend

`MAPPED_TO_EXISTING` · `IMPLEMENTED` (UX connected to the existing capability) ·
`IMPLEMENTED_END_TO_END` (new schema/API/frontend/test path) ·
`HONESTLY_UNAVAILABLE` (truthful unavailable state) ·
`REMOVED_AS_UNSUPPORTED` (conflicts with RACEWISE truth; listed as FABRICATED STITCH DATA where Stitch invented values)

---

## 1. Engineering Command Center

| # | STITCH FEATURE | EXISTING RACEWISE CAPABILITY | EXISTING API/TOOL | FINAL STATUS | WHAT SHIPS |
|---|---|---|---|---|---|
| 1.1 | NEW INVESTIGATION primary button | Investigation launcher | — (frontend → `GET /api/catalog/engineering-investigation`) | MAPPED_TO_EXISTING | Sidebar button routes to the real launcher |
| 1.2 | Navigation deck (10 destinations) | Hash-routed views | `App.tsx` NAV | IMPLEMENTED | Stitch nav vocabulary maps 1:1 onto real views; Active Investigation = the 6N flagship |
| 1.3 | Data sync footer (FastF1 v3.4.1, 42k slices, Sakhir LAN) | Real catalog status | `GET /api/catalog/sessions?capability=telemetry` | REMOVED_AS_UNSUPPORTED | Only real counts (sessions with telemetry capability); test 1.3-guard bans the fabricated strings |
| 1.4 | Header crumb + fake hash `#8F3A2E` + `SYNCED [99.8%]` | Real scope crumb; real `output_hash` per run | engineering-investigation payload | IMPLEMENTED | Real scope in the header; real investigation hash shown when a run exists; no sync percentage |
| 1.5 | Header weather chip | Real per-session weather rows | **NEW** `GET /api/catalog/session-context` | IMPLEMENTED_END_TO_END | Measured air/track temps (first→last observation) rendered in the context strip; honest `weather not recorded` when absent |
| 1.6 | NL engineering query console | Phase 6T autonomous investigation | `POST /api/investigations/autonomous` | IMPLEMENTED | Console in the command center; real stage ledger, run id, engine ref; real 422/409 surfaces |
| 1.7 | Context preset selectors | Launcher scope controls + catalog | `GET /api/catalog/sessions` | MAPPED_TO_EXISTING | Launcher controls kept; templates prefill them |
| 1.8 | Fast Investigation Templates (7 pills) | Real question types (closed vocabulary) | engineering-investigation | IMPLEMENTED | 8 template pills — LAP_PERFORMANCE, STINT_PERFORMANCE, RACE_GAP, PERFORMANCE_REGIME, CROSS_RACE_PATTERN, HYPOTHESIS_EVALUATION, COUNTERFACTUAL_ELIGIBILITY, Qualifying lap — each prefills the real launcher; nothing beyond the engine vocabulary is offered |
| 1.9 | Active Investigations Ledger table | Recents (real runs, client-saved) | frontend recents from real runs | IMPLEMENTED | Real conclusion states, evidence counts, measured delta, unassigned residual, per-hypothesis state dots from the run; fabricated "Lead" column and INV ids removed; recency sort only |
| 1.10 | SORT: CONFIDENCE DESC | none (no composite confidence) | — | REMOVED_AS_UNSUPPORTED | No confidence sorting exists or is offered |
| 1.11 | Focused Trace Preview | Real comparison windows | `GET /api/catalog/telemetry-comparison` | IMPLEMENTED | Selecting a recent loads the real per-window estimated losses as bar heights; honest note when unavailable |
| 1.12 | Telemetry Slices card (corner speed, thermal, ERS SOC) | Real channels: speed, throttle, brake, gear, rpm, drs | session-context telemetry coverage | REMOVED_AS_UNSUPPORTED | Tyre temperature / ERS SOC / corner-station metrics do not exist in the corpus; real coverage facts (`covered laps · 0.25 s grid`) shown instead |
| 1.13 | Candidate Hypotheses `FALSIFIED (99%)` etc. | Real hypothesis evaluations | engineering-investigation payload | REMOVED_AS_UNSUPPORTED | Percentages never rendered; real canonical states shown per run (ledger dots) |
| 1.14 | ENTER COUNTERFACTUAL LAB | Counterfactual lab route | `#/counterfactual` | MAPPED_TO_EXISTING | Kept (also reachable from the synthesis actions) |
| 1.15 | Footer "1,420 solved investigations" / `0x9F4C…` / team nodes | Real catalog counts; per-run hashes | catalog sessions | REMOVED_AS_UNSUPPORTED | Only real counts and real hashes; no team-branding nodes |

## 2. Active Investigation Workspace (flagship, v1/v2/v3)

| # | STITCH FEATURE | EXISTING RACEWISE CAPABILITY | EXISTING API/TOOL | FINAL STATUS | WHAT SHIPS |
|---|---|---|---|---|---|
| 2.1 | Hero: dominant question + epistemic state | Investigation hero | engineering-investigation payload | MAPPED_TO_EXISTING | Real question, real conclusion-state chip, real investigation id |
| 2.2 | Context strip: compound/tyre age/position per driver | Real stints + per-lap facts | **NEW** `GET /api/catalog/session-context` (+ `drivers=`) | IMPLEMENTED_END_TO_END | Real measured chips (P · compound · tyre life) at the investigated lap; honest `lap context not in canonical rows` otherwise |
| 2.3 | RUN_ID chip | Real content-hash investigation id | payload | MAPPED_TO_EXISTING | Real id + copy action (with real clipboard feedback) |
| 2.4 | KPI: Observed Gap | Real 6E observed delta evidence | evidence ledger (stable engine claims) | IMPLEMENTED | Value + evidence id extracted from the ledger; omitted when absent |
| 2.5 | KPI: Comparable VALID | Real 6E attribution status | `GET /api/catalog/attribution/{season}/{round}` | IMPLEMENTED | Real verdict chip (`VALID_COMPARISON`, `VALID_WITH_CAVEATS`, `INSUFFICIENT_EVIDENCE`, `UNAVAILABLE`) with the engine reason; nothing rendered for out-of-scope questions |
| 2.6 | KPI: Evidence triage `8 / 12` | Real ledger counts | payload | MAPPED_TO_EXISTING | `n / ledger-length evaluated` |
| 2.7 | KPI: epistemic state + `P=0.74` | Real conclusion state | payload | IMPLEMENTED | State kept; probability removed (banned by the fabrication guard) |
| 2.8 | KPI: Unresolved Residual | Real 6E residual evidence item | ledger (`unexplained residual component`) | IMPLEMENTED | Real value + `UNRESOLVED — never assigned to a mechanism` |
| 2.9 | KPI: Falsification Score 78% bar | none | — | REMOVED_AS_UNSUPPORTED | Never rendered; the real falsification gate is displayed |
| 2.10 | Channel toggles ("All Channels (14)") | 6 real channels | telemetry policy | MAPPED_TO_EXISTING | Speed traces + throttle/brake window deltas (the channels with real comparison semantics); no "14 channels" claim |
| 2.11 | "100 Hz Interpolated" | 0.25 s analysis grid reality | `profile_samples.sampling`, session-context | REMOVED_AS_UNSUPPORTED | Honest `0.25 S ANALYSIS GRID` + "native ~0.16–0.40 s samples resampled" caption; fabrication-guard bans `100 Hz` |
| 2.12 | Synchronized speed traces + crosshair | Engine computes aligned profiles | **NEW** opt-in `include_profile` | IMPLEMENTED_END_TO_END | Real aligned target/reference traces, deficit-region shading, crosshair with real readouts (t, speeds, Δv) |
| 2.13 | Turn/station annotations (3,240 m etc.) | Distance channels explicitly NOT ingested | telemetry policy | HONESTLY_UNAVAILABLE | The x-axis is the honest lap-relative time grid; no invented corners/stations |
| 2.14 | Mini correlation sparklines (steer slip, MGU-K) | Throttle/brake window associations only | telemetry-comparison | REMOVED_AS_UNSUPPORTED | Steering/MGU-K channels don't exist; real per-window deltas rendered |
| 2.15 | "LINKED CLAIM" HUD | Real evidence ids | ledger | MAPPED_TO_EXISTING | Real evidence-id linkage kept (hover-highlight ↔ ledger) |
| 2.16 | Hypothesis Matrix H1–H6 | Real hypothesis evaluations | payload | MAPPED_TO_EXISTING | Canonical states + coverage counts, clickable → graph focus |
| 2.17 | Per-hypothesis contribution seconds | none — deliberately unassigned | — | REMOVED_AS_UNSUPPORTED | The engine never assigns evidence to hypotheses as causal contribution |
| 2.18 | Evidence inspector drawer | Contextual inspector + provenance | ledger + graph evidence trace | MAPPED_TO_EXISTING | Real claim/type/class/value/state/hypotheses/assumptions/limitations + trace-to-source |
| 2.19 | "VERIFIED P=0.98" | none | — | REMOVED_AS_UNSUPPORTED | Banned by the fabrication guard |
| 2.20 | "Falsify Claim" button | Falsification is engine-run | falsification gate | REMOVED_AS_UNSUPPORTED | Dead control removed; falsification surfaces via the real gate + matrix view |
| 2.21 | Decision trace workflow strip | Real lifecycle + decision trace | payload | MAPPED_TO_EXISTING | Phase timeline (derived from real content) + trace list with basis links |
| 2.22 | Synthesis verdict + "CONFIDENCE 94.2%" | Real synthesis | payload | IMPLEMENTED | Real conclusion state, findings, unresolved questions; confidence removed |
| 2.23 | "PUBLISH VERDICT" | No publish/sign-off operation | — | REMOVED_AS_UNSUPPORTED | Replaced by real actions: Export investigation (JSON), Replay, Open counterfactual lab |
| 2.24 | "SPAWN SUB-INVESTIGATION" | No autonomous spawn | — | REMOVED_AS_UNSUPPORTED | Follow-ups are launched through the real launcher (recents keep the scope) |
| 2.25 | Residual "prompts automatic background ingest" | No background ingest exists | — | REMOVED_AS_UNSUPPORTED | Residual stays `UNRESOLVED`; no invented mechanism or auto-follow-up |
| 2.26 | Degradation context (slope per compound/age) | Real 6G stint evidence | `GET /api/catalog/stint-evidence` | IMPLEMENTED | Real compounds, stint windows, OLS slope; `INSUFFICIENT_EVIDENCE` shown when the engine says so |
| 2.27 | Replay button | Real deterministic replay | `GET …/engineering-investigation/replay` (ReplayPanel) | IMPLEMENTED | Synthesis action scrolls to the real replay panel (re-run + hash comparison) |
| 2.28 | "DUAL VERIFIED [FIA+FASTF1]" | Real provider provenance | payload provenance | REMOVED_AS_UNSUPPORTED | Only the real provider provenance is shown |

## 3. Falsification Matrix

| # | STITCH FEATURE | EXISTING RACEWISE CAPABILITY | EXISTING API/TOOL | FINAL STATUS | WHAT SHIPS |
|---|---|---|---|---|---|
| 3.1 | Protocol header + provenance ref | Real investigation id/hash | payload | MAPPED_TO_EXISTING | Real ids rendered |
| 3.2 | Summary cards (hypotheses/contradicted/supported/partial) | Real aggregate-state counts | hypothesis_evaluations | IMPLEMENTED | Counts computed client-side from the payload only |
| 3.3 | "100Hz FastF1 Array" | 0.25 s grid | telemetry policy | REMOVED_AS_UNSUPPORTED | Banned; honest grid facts only |
| 3.4 | Matrix: hypothesis / prediction / criterion / evidence / verdict | Statements (6F HYPOTHESES), documented evaluation rules, real evidence lists, canonical verdicts | engineering-investigation | IMPLEMENTED | Dedicated `FalsificationMatrixView`: engine statement + engine evaluation rule (methodology) + clickable evidence-id chips per class + `aggregate_state`/gate chips; statements/rules mirrored from `evidence_fusion.py` and pinned by tests |
| 3.5 | "CONFIDENCE: 94.2%" per hypothesis | none | — | REMOVED_AS_UNSUPPORTED | Banned |
| 3.6 | Expanded rows (steering lock, lateral accel) | No such channels | — | REMOVED_AS_UNSUPPORTED | Expanded rows list the real evidence items (claim, value, state, class) |
| 3.7 | ALL / FALSIFIED filters | Client filtering of real rows | — | IMPLEMENTED | `ALL` / `CONTRADICTED` filters over real `aggregate_state` |
| 3.8 | RUN GATES button | Gate computed per run | falsification gate | IMPLEMENTED | "Re-run investigation (deterministic)" — no fake async animation |
| 3.9 | Decision trace timeline rail | Real decision trace | payload | IMPLEMENTED | Numbered steps, real statements, basis links opening the evidence drawer |
| 3.10 | Epistemic synthesis bar | Real synthesis + boundaries | payload | IMPLEMENTED | Real conclusion state + unresolved questions; non-causal phrasing enforced |
| 3.11 | EXPORT AUDIT / SIGN OFF | Real verbatim export exists; no sign-off | — | IMPLEMENTED (export) / REMOVED (sign-off) | Export = verbatim payload download |
| 3.12 | Popper asymmetry callout | Real epistemic boundaries list | payload | MAPPED_TO_EXISTING | Engine's own boundaries rendered |

## 4. Counterfactual Lab

| # | STITCH FEATURE | EXISTING RACEWISE CAPABILITY | EXISTING API/TOOL | FINAL STATUS | WHAT SHIPS |
|---|---|---|---|---|---|
| 4.1 | "MODELLED · SYNTHETIC RUN" badge | Real epistemics | payload | MAPPED_TO_EXISTING | `MODELLED · NOT HISTORICAL` badge + engine epistemics sentence |
| 4.2 | "SOLVER: AERO-DELTA v2.1.4" | Real method: fixed-distance integration | payload model | REMOVED_AS_UNSUPPORTED | Real method + version + alignment rendered |
| 4.3 | Simulation-mode banner (100 Hz claim) | Real method + honest grid | payload | IMPLEMENTED | Banner with corrected 0.25 s grid description |
| 4.4 | "RESIDUAL TOLERANCE ±0.004s" | Real gate 5 detail (1e-6 s reproduction) | validation gates | REMOVED_AS_UNSUPPORTED | Real gate detail rendered instead |
| 4.5 | KPI ribbons | Real modeled lap times, delta, deficit closed, gate counts | payload | IMPLEMENTED | All ribbons from real fields; `6 / 6 PASS` computed from gates |
| 4.6 | Baseline/target lap-time card | Real model baseline + measured grid duration | payload | MAPPED_TO_EXISTING | Real values with reproduction error |
| 4.7 | λ slider | Real `fraction` param | `GET …/counterfactual?fraction=` | MAPPED_TO_EXISTING | Real slider + driver/reference/lap controls |
| 4.8 | Affected spatial sector (2,150 m→3,890 m) | No distance axis | counterfactual model | HONESTLY_UNAVAILABLE | Affected region described on the time grid (deficit shading from real samples) |
| 4.9 | Formulation `v_cf = v + λ·max(0, v_ref − v)` | Exact engine definition | `intervention_definition` | MAPPED_TO_EXISTING | Engine's real definition string |
| 4.10 | Physical validation gates (LatG/thermal/MGU-K) | Real 6 engine gates | `validation_gates` | REMOVED_AS_UNSUPPORTED (values) / IMPLEMENTED (gates) | Real gate names, PASS/FAIL statuses and engine detail |
| 4.11 | Speed profile canvas | Engine-computed aligned profiles | **NEW** opt-in `include_profile` | IMPLEMENTED_END_TO_END | Baseline/reference/counterfactual traces on the real time grid; crosshair readouts; MODELLED labelling |
| 4.12 | Station inspection matrix | Crosshair HUD samples real traces | (4.11) | MAPPED_TO_EXISTING | The crosshair gives per-time-point baseline/reference/Δv/counterfactual readouts |
| 4.13 | Sensitivity curve + ledger (λ sweep) | Real 6J bounded scenario sweep | `GET …/performance-envelope?scenario_type=DEFICIT_REDUCTION` | IMPLEMENTED | Real scenario points (parameter, modeled lap time, delta) + real response classification; the active fraction row is highlighted |
| 4.14 | "Aero Elasticity Note" | No aero model | — | REMOVED_AS_UNSUPPORTED | Engine's real sensitivity note rendered |
| 4.15 | "8-CORE NUMERICAL", "RUN #0492-CF" | Single deterministic integration | payload | REMOVED_AS_UNSUPPORTED | Real method + real output hash |
| 4.16 | Re-calculate / Export buttons | Real re-run + verbatim export | counterfactual API | MAPPED_TO_EXISTING | Wired to the real fetch + JSON download |

## 5. Cross-cutting design system (DESIGN.md)

| # | STITCH FEATURE | FINAL STATUS | WHAT SHIPS |
|---|---|---|---|
| 5.1 | Surface ladder, hairline borders, cyan accent | MAPPED_TO_EXISTING | Token layer + contract tests |
| 5.2 | Epistemic state engine colors | MAPPED_TO_EXISTING | Tokens + `ef-badge`/`claim-tag` chips |
| 5.3 | Inter + JetBrains Mono, tabular numerals, caps micro-labels | MAPPED_TO_EXISTING | Font tokens; all new metrics mono |
| 5.4 | 4/8px cadence, 0px panels / 4px interactive | MAPPED_TO_EXISTING | Spacing + radius tokens |
| 5.5 | Instrument-style charts, dense tables, left-accent focus | IMPLEMENTED | New canvas/matrix/lab components use the same language |
| 5.6 | Responsive tri-pane → drawer → single column | MAPPED_TO_EXISTING | `@media` collapse points for the new layouts (fm-body/cf-columns at 1180px) |
| 5.7 | Material Symbols icons | MAPPED_TO_EXISTING | tabler icon family kept (no CDN fonts in production) |

## 6. Navigation / shell

| # | STITCH FEATURE | FINAL STATUS | WHAT SHIPS |
|---|---|---|---|
| 6.1 | Command palette (⌘K) | MAPPED_TO_EXISTING | Real typed search + navigation |
| 6.2 | "Causal Graph DAG" label | REMOVED_AS_UNSUPPORTED | Route is the real `Investigation Graph` (6P); fabrication-guard bans causal-graph labels |
| 6.3 | Export buttons | MAPPED_TO_EXISTING | Verbatim JSON exports |
| 6.4 | Status bar with real state | MAPPED_TO_EXISTING | Deterministic-chain status + real recents count |

---

## Backend extensions delivered (§31, all additive)

1. **`GET /api/catalog/session-context/{season}/{round}`** — measured stints, per-lap facts (`position`, `time_s`, `compound`, `tyre_life` for ≤ 4 requested drivers), weather summary, telemetry coverage + provenance. Composed from existing `canonical_queries` methods; honest `UNAVAILABLE` facets; closed `session_type` vocabulary (422 otherwise). 16 tests.
2. **Opt-in `include_profile` on `GET /api/catalog/counterfactual`** — bounded (cap 192) deterministic decimation of the aligned speed profiles (`t_s`, `target_kmh`, `reference_kmh`, `counterfactual_kmh`), inserted before hashing so the hash always covers the returned content. **Default OFF keeps the canonical payload and every golden hash byte-identical** (the version was deliberately NOT bumped; a first-pass bump was caught by the golden tests and reverted). Display-only; the model integrates the full grid.

No existing endpoint, vocabulary, payload, hash or behavior changed otherwise.

## Test coverage delivered

- **Backend:** 801 tests total (786 pre-existing + 15 new for the two extensions). Determinism goldens intact (`IDENTICAL` replay verified live).
- **Frontend:** 70 tests (12 design-system + 58 new): navigation-vocabulary contract, flagship rendering (observed delta, unassigned residual, context strip, identity-fraction profile fetch, degradation context, hypothesis matrix, decision trace, synthesis, honest error states, qualifying non-substitution), falsification matrix (all canonical states, counts, evidence drawer, filters, synthesis honesty), counterfactual lab (MODELLED labels, real ribbons/gates/sweep, honest UNAVAILABLE, provenance), command center (templates, 6T console + honest 422, enriched ledger, focused trace preview, no fabricated counts), fabrication guard over all production sources, responsive component classes.
- **Live E2E (running stack):** health, session-context (real rows), counterfactual default-vs-profile hashes, envelope sweep, 6N investigation, 6O replay `IDENTICAL`, 6P graph, honest 404/422, memory, search — 12/12 PASS.

## Remaining limitations (honest)

- Trace plots cover **speed** (aligned profiles) and throttle/brake **window deltas**; gear/rpm/drs traces exist in the corpus but are not plotted — the UI does not imply otherwise.
- No distance/corner axis exists anywhere (positional channels are not ingested by policy); all telemetry x-axes are lap-relative time on the 0.25 s analysis grid.
- The 6T autonomous console requires a configured model provider; without one it surfaces the real failure state rather than a simulated answer.
- Recents are per-browser (real runs saved client-side); there is no server-side investigation registry by design (scope-addressed content hashes).

**Final status: READY_FOR_STITCH_INTEGRATED_RACEWISE**
