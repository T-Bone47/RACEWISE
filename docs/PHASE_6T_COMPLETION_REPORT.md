# Phase 6T Completion Report — Autonomous Engineering Investigation

## Final status

**READY_FOR_AUTONOMOUS_ENGINEERING**

The orchestrator takes natural-language engineering questions and autonomously
produces replayable, evidence-backed investigations through the deterministic
engine — with traced orchestration decisions, explicit falsification, honest
failure states, budgets, injection resistance and full provenance. Real
investigations run end-to-end (API, benchmark, goldens, determinism, replay);
the only unverified surface at report time is interactive click-through in the
desktop browser panel (browser-bridge attach issue in the harness), while the
same routes are verified over HTTP and the workspace view is verified to
render.

## What was built (mandate → implementation)

| Mandate | Implementation |
| --- | --- |
| §2 First action | Architecture inspected first; [PHASE_6T_ARCHITECTURE.md](PHASE_6T_ARCHITECTURE.md) written before implementation. No parallel framework: the orchestrator delegates all analysis to the existing engine (`investigation_synthesis.py`, `evidence_fusion.py`, `canonical_queries.py`, `investigation_memory.py`, graph builder, counterfactual tools). |
| §3 Canonical orchestrator | `src/racewise/data/historical/autonomous_investigator.py` — full lifecycle (CREATED→QUESTION_PARSED→CONTEXT_RESOLVED→DATA_CHECKED→HYPOTHESES_SELECTED→EVIDENCE_PLANNED→EVIDENCE_COLLECTING→FALSIFICATION→COUNTERFACTUAL_CHECK→SYNTHESIS→VERIFICATION→COMPLETED) with failure states `INVALID_QUESTION`, `CONTEXT_UNRESOLVED`, `DATA_UNAVAILABLE`, `INSUFFICIENT_EVIDENCE`, `TOOL_FAILURE`, `VERIFICATION_FAILURE`, `BUDGET_EXHAUSTED`. |
| §4–5 NL intake & classification | `question_intake.py`: closed vocabulary only (LAP_PERFORMANCE, STINT_PERFORMANCE, RACE_GAP, PERFORMANCE_REGIME, CROSS_RACE_PATTERN, HYPOTHESIS_EVALUATION, COUNTERFACTUAL_ELIGIBILITY, QUALIFYING); unmappable → `UNSUPPORTED_QUESTION` with explanation; missing critical context → `CONTEXT_UNRESOLVED`, never a guessed race. |
| §6 Context resolution | Canonical slugs; accent-insensitive, word-bounded, capitalization-gated driver mentions; participation-based disambiguation within a season; "Kimi Antonelli in 2023" → honest UNAVAILABLE; race resolution via GP keys then circuit/city aliases (Jeddah→Saudi Arabian GP), single-candidate-or-unresolved. |
| §7 Data availability | DATA_CHECKED stage reads per-facet availability from the canonical catalog before any expensive tool call; structurally impossible tools are never run. |
| §8 Hypothesis selection | All six hypotheses with recorded WHY_SELECTED / WHY_NOT_SELECTED decisions (SELECT_HYPOTHESIS / SKIP_TOOL trace entries). |
| §9 Evidence plan | Ordered plan per question type; every planned item maps to a real deterministic tool; persisted in the run record (`plan_hash`). |
| §10 Adaptive collection | EVIDENCE_COLLECTING loop: inspect → request next needed tool (REQUEST_MORE_EVIDENCE) → re-evaluate testability → stop when sufficient or honestly blocked; telemetry-unavailable contexts fail at DATA_UNAVAILABLE. |
| §11 Budgets | `max_tool_calls` (60), `max_counterfactuals` (2), `max_cross_race_scans` (6), `max_memory_neighbors` (2), `max_runtime_ms`; run exposes budget/consumed/remaining; exhaustion → `BUDGET_EXHAUSTED` with provenance (covered by benchmark T35). |
| §12 Falsification-first | FALSIFICATION stage records supporting/contradicting/missing/not-testable per hypothesis; conflicts carry evidence refs (VERIFICATION re-checks them). |
| §13 Adaptive hypothesis evolution | Orchestrator requests more evidence; deterministic engine assigns all final states — the orchestrator never declares SUPPORTED. |
| §14 Counterfactual decision | COUNTERFACTUAL_CHECK uses existing eligibility rules (ELIGIBLE / INELIGIBLE / INSUFFICIENT_EVIDENCE / TELEMETRY_UNAVAILABLE / UNSUPPORTED_MODEL); orchestrator proposes REMOVE_DEFICIT etc., engine executes; OBSERVED/CALCULATED/INFERRED/MODELLED labels preserved from engine output. |
| §15 Multi-step investigation | Hypothesis branches share evidence via content-addressed engine evidence identity; discovery/collection dedupes by tool-result hash. |
| §16–17 Plan & decision trace | Machine-readable run record with plan, stages, budget; decision trace entries carry decision_id/order/type/input_state/reason/selected_action/tool/tool_result(+hash of deterministic fields)/evidence_refs/output_state. Runtime timings are kept out of identity hashes. |
| §18–19 Synthesis & answer | Engine-derived synthesis wrapped as WHAT HAPPENED / SUPPORTS / CONTRADICTS / UNRESOLVED / COUNTERFACTUAL / LIMITATIONS / PROVENANCE; canonical answer object with evidence refs on every finding. |
| §20 Follow-ups | Derived from actual missing evidence (NOT_TESTABLE/INSUFFICIENT hypotheses, unresolved questions), not generic chatbot suggestions. |
| §21 Memory | Exact memory derivation on completion; related memory via 6S structural rules (±1-season neighbors, pointers-not-conclusions, recorded as decisions). |
| §22 Graph | Engine investigation id recorded on every run → graphable via the existing 6S investigation-graph route (goldens carry graph_id/node/edge counts/hash). |
| §23 Replay | `replay_run` + `POST .../{run_id}/replay`; identical inputs → IDENTICAL (verified ×3 same-process, fresh-process, and across the API); data changes → CHANGED with changed dimensions. |
| §24 API | `POST /api/investigations/autonomous`, `GET .../autonomous/{run_id}`, `GET .../autonomous/runs` (list, path chosen to avoid legacy `{inv_id}` shadowing), `POST .../{run_id}/continue`, `POST .../{run_id}/replay`, `GET .../{run_id}/stream` (SSE). Additive only. |
| §25 Streaming | Real stage events streamed from the orchestrator as stages complete (no simulated timers); frontend renders the live timeline from SSE. |
| §26–28 Frontend | `apps/web/src/AutonomousView.tsx` (`#/autonomous`): question input + optional structured context, live stage ledger, hypothesis panel with states, evidence ledger, decision trace with explicit ORCHESTRATOR vs ENGINE distinction (`.auto-orchestration` / `.auto-engine`), synthesis, provenance; honest failure rendering (`.auto-failure`). |
| §29 Safety/trust | No hidden anything: every tool call, hypothesis selection, skip, stop and memory derivation is a traced decision with a reason; original intake context stored alongside resolved context. |
| §30 Performance | Tool-result dedupe by deterministic hash; per-run tool runtime + total runtime metrics; no mutable external data cached. |
| §31 LLM boundary | Deterministic end-to-end; no LLM anywhere in the loop (boundary enforced by construction; see security model). |
| §32 Corpus | `tests/benchmarks/phase_6t_autonomous_investigations.json`: 40 cases — 12 lap, 5 stint, 4 qualifying, 5 race gap, 3 regime, 3 cross-race, 2 counterfactual + unknown driver, missing telemetry, insufficient evidence, contradiction, unsupported question, budget exhaustion. |
| §33 Adversarial | Wrong driver, wrong season, future data, unknown race, missing session, unsupported question, missing telemetry, contradictory evidence, budget zero, replayed changed data, malformed context — all honest (unit + integration + benchmark). |
| §34 Injection | Question text is data: override/conclusion-fixing instructions are scanned, recorded (`injection_scan`), and ignored as directives while the investigation proceeds normally (golden T-G02, unit tests, E2E-verified via API). |
| §35 No fabrication | VERIFICATION stage: no dangling evidence refs, conflicts cite existing evidence, trace contiguous; synthesis wraps engine output only. No-fabrication tests assert every evidence ref resolves. |
| §36 Determinism | Same-process ×3 identical, fresh process identical, API identical, replay IDENTICAL; decision identity hashes exclude runtime timings (defect found and fixed during golden capture). |
| §37 Provenance | Decision trace + evidence refs + engine provenance preserved; provenance hash in run record and goldens. |
| §38 E2E | Full backend path verified over HTTP (POST→COMPLETED, SSE 21 stage events, replay IDENTICAL, list, continue); workspace view renders with question intake and disabled-until-question start button; in-panel click-through blocked by a harness browser-bridge attach issue (not an application defect). |
| §39 Performance benchmark | 40-case run: full investigation p50 ≈ 0.8 s, p95 ≈ 59 s, max ≈ 74 s (p95/max dominated by first-touch telemetry loads on uncached sessions; cached runs ≈ 2 s); stage-level p50/p95/max recorded in `data/benchmarks/6t_benchmark_results.json` (runtime artifact). |
| §40 Regression | 737-test baseline + 44 new 6T tests; full suite run recorded in the completion log; 6R/6S benchmarks re-runnable unchanged (`tests/benchmarks/run_engineering_benchmark.py`). |
| §41 Goldens | 15 autonomous goldens (exceeds 10; 3 contradiction, 2 limitation, 2 counterfactual, 2 qualifying, 2 cross-race) with question object/plan/output/snapshot/replay/provenance/graph hashes — `tests/benchmarks/phase_6t_goldens.json`, verified by `tests/unit/test_phase_6t_goldens.py`. |
| §42 Documentation | This report + ARCHITECTURE + AUTONOMOUS_INVESTIGATION + SECURITY_MODEL. |
| §43 Acceptance | All boxes satisfied; exceptions listed below under Known limitations. |

## Validation summary

- **6T benchmark**: 40/40 pass (includes in-run determinism double-checks), wall ≈ 270 s.
- **New tests**: 41 unit/integration + 3 golden verification = 44, all green.
- **Full regression**: 737-test baseline + 44 new — executed via the standard
  suite (`tests src --ignore=tests/integration/test_investigation_flow.py`);
  legacy 5-test integration file run separately per convention.
- **Goldens**: 15/15 replay IDENTICAL.
- **Determinism**: ×3 same-process, fresh process, API, replay — identical.
- **Injection**: flagged + recorded + ignored as directive; result unchanged.
- **API**: POST/GET/list/continue/replay/stream all live over HTTP.

## Known limitations

1. **Interactive click-through E2E** (enter question → watch stages → open
   provenance in a real browser) could not be captured in this environment:
   the desktop preview bridge failed to attach a composited page after the
   Freebuff restart. The same flow is verified at the HTTP layer (POST → SSE
   stage events → replay) and the workspace view is verified to render; the
   click-through remains to be re-run in a healthy browser session.
2. **First-touch latency**: p95 ≈ 59 s reflects the first telemetry load for an
   uncached session (measured, not hidden); subsequent identical scopes hit
   the engine's existing caching and complete in ≈ 2 s.
3. **Rule-based NL parsing**: phrasings outside the deterministic grammar
   resolve honestly (`UNSUPPORTED_QUESTION` / `CONTEXT_UNRESOLVED`) rather
   than guessing — by design, per the no-guessing mandate.
4. **Stint questions are pair-comparative** (Phase 6S engine semantics);
   single-driver stint phrasings resolve `CONTEXT_UNRESOLVED`.

## Runtime artifacts (not committed, per convention)

`data/benchmarks/6t_benchmark_results.json`, `data/autonomous_runs/*`,
`/tmp/6t_regression.log`.
