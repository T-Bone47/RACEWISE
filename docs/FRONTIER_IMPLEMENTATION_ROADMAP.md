# RACEWISE Frontier Implementation Roadmap

**Date:** 2026-10-14
**Baseline commit:** 098831a

---

## Phase 0 — Preserve, Inventory, Baseline ✅

**Status:** COMPLETE

- Repository verified and synchronized with remote
- Full documentation audit complete
- Baseline tests run (backend: 62 passed/2 skipped; frontend: 136 passed)
- Benchmark baseline recorded (23 questions, 230 corpus, 62.2% pass rate)
- This document created

## Phase 1 — Intelligence Evaluation Foundation ✅

**Status:** COMPLETE

- Failure taxonomy created from 87 failing cases (`docs/FRONTIER_FAILURE_TAXONOMY.md`)
- Race-grouped holdout set created (`tests/benchmarks/holdout_set.json`)
- Evaluation report generator built (`scripts/evaluation_report.py`)
- Corpus measurement harness (`scripts/measure_corpus.py`) — reproducible before/after metrics
- Exit criteria met: the system can be measured before and after changes with reproducible results.

## Phase 2 — Core Investigation Quality ✅

**Status:** COMPLETE

- Question engine pass rate: **62.2% → 99.1% (228/230)**
- Cross-race: 0/8 → 8/8 (intents attached on every compile path)
- Qualifying: 0/5 → 5/5 (engine-anchored representative qualifying lap)
- Compound: 3/14 → 13/14 (follow-up context fix)
- Degradation: 15/28 → 28/28 (degrad/evol(u|v) stem fixes)
- Falsification: 10/17 → 17/17 (ruled-out/refute/counter-evidence vocabulary)
- Ambiguous: 6/10 → 10/10 (hypothesis disjunctions + "same thing" pattern)
- Historical: 2/9 → 8/9 (GP-name resolution + era context)
- All 154 question-engine tests pass; all 15 goldens reproduce identically; frontend 136/136.
- Remaining 2 are genuine edge cases (single-driver stint comparison; a single-ask compound expectation).
- Exit criteria met: demonstrable improvement without regressions in frozen evaluation set.

## Phase 3 — Model Tuning Decision ✅

**Status:** COMPLETE — **Decision: NO fine-tuning. The investigation path is fully deterministic.**

**Evidence (audited this phase):**
1. `InvestigationEngine` (`investigation/engine.py`) accepts `provider: ModelProvider | None`
   and stores `self.provider` (line 53) but **never calls `.respond()`** — the LLM is dead
   code in the investigation run loop. Every number comes from deterministic tools.
2. `autonomous_investigator.py` — which executes the corpus and all 15 goldens — has
   **zero** provider/LLM/model references. It is fully deterministic.
3. **No prompt templates exist** anywhere in `src/` (audited via prompt-template search).
4. `.respond()` is **never called** on any provider in the entire `src/` tree — the only
   grep hits are the English word "respond" in docstrings.
5. The corpus reached 99.1% (228/230) through deterministic routing/context fixes. The
   original failures were routing and context-resolution problems — engine logic, not
   prose parsing — so a model could not have fixed them and fine-tuning has no target.

**Decision:** Fine-tuning is **not justified**. There is no LLM in the investigation path
to tune, and the design principle "the deterministic engine owns all computation; the LLM
never invents numbers" is already enforced by construction. The `ModelProvider` protocol
and `UnionAlphaProvider` (OpenRouter) remain an optional, configured-but-unused extension
point for a future conversational layer — not a tuning target.

**Model-dependent evaluation:** the LLM-judged dimensions cannot be scored without
`OPENROUTER_API_KEY`, but this is moot: no model is invoked in the investigation pipeline,
so there is nothing model-dependent to measure. All scored dimensions are deterministic.

**Exit criteria met:** evidence-backed model strategy documented; no fine-tuning falsely
claimed.

## Phase 4 — Integration and Specialist-Tool Boundaries ✅

**Status:** COMPLETE

**Evidence (audited and tested this phase):**
1. **evidence_v1 contract — verified.** Every evidence stream is
   internally versioned and deterministic:
   `6m_evidence_v1` (cross-race), `stint_evidence_v1` (stint),
   `q9_stint_evidence_v1`, `q15_cross_race_evidence_v1`. 136
   contract tests pass (`test_evidence_fusion`,
   `test_performance_evidence`, `test_stint_evidence`,
   `test_simulator`, `test_counterfactual`).
2. **No blind duplication.** Each capability has one authoritative
   owner: `loss_attribution` owns attribution, `evidence_fusion`
   owns fusion, `performance_patterns` owns patterns. The fusion
   module "consumes Phase 6L patterns verbatim — no second pattern
   matcher, no second evidence-fusion engine."
3. **No semantic drift.** The fusion layer's evidence states
   (`SUPPORTED/CONTRADICTED/NOT_SUPPORTED/NOT_TESTABLE` and
   relationship `SUPPORTS/CONTRADICTS/DOES_NOT_TEST`) are a
   deliberately richer, documented vocabulary than the domain
   `EvidenceRelationshipType` enum. `DOES_NOT_TEST`/`NOT_TESTABLE`
   are honest abstention states ("required evidence unavailable"),
   distinct from `NOT_SUPPORTED` — an invariant, not drift.
4. **Simulator boundary — justified and preserved.** `simulate_pit_timing`
   (`racewise.simulator.strategy`, `SIMULATOR_VERSION="1.0.0"`) is an
   INTERNAL deterministic counterfactual model, explicitly "NOT a
   physics simulator": it replays observed laps, applies interventions,
   and reports deltas under stated assumptions, always labeled
   COUNTERFACTUAL. The external **F1 Pro Simulator** and **Live F1
   Intelligence** remain separate repositories — RaceWise consumes
   fastf1 data (`provider="fastf1"`) but absorbs neither.

**Exit criteria met:** contracts tested (136 passing); no blind
duplication; no semantic drift; specialist-tool boundaries preserved.

## Phase 5 — Design System and UI/UX Audit ✅ (audit) / ⛔ (skill work — gated on authorization)

**Status:** AUDIT COMPLETE — the design system is implemented and
pinned by tests. UI/UX-skill installation is **gated on user
authorization** (per the standing constraint: "install/use UI/UX
skills only after inspecting format/compatibility and obtaining
user authorization").

**Audit evidence (verified this phase):**
1. **Design system is comprehensive and authoritative.**
   `DESIGN.md` (tokens, palette, typography, chart language,
   motion) + `docs/RACEWISE_DESIGN_SYSTEM.md` (component &
   convention reference, IA, flagship layout).
2. **Tokens are implemented and pinned against drift.**
   `apps/web/src/App.css` `:root` holds the Stitch surface
   ladder (`#0b0e12…#232934`), signal accents (cyan/indigo),
   and the epistemic state engine. `design-system.test.ts`
   (31 tests, passing) pins them and **enforces the fabrication
   guard**: legacy tokens alias to Stitch values, F1-red
   (`#e10600`) is asserted absent, epistemic states are pinned.
3. **App shell is pinned.** `app-shell.test.tsx` asserts every
   documented route is reachable from the deck.
4. **All views are implemented.** 19 view components map 1:1 to
   the documented IA (Command, flagship Investigation,
   Falsification, Counterfactual, Telemetry, Attribution,
   Fusion, Stint, RaceGap, Envelope, Regime, Patterns,
   PatternEvidence, Catalog, Autonomous, Compare, Replay).
5. **Grounding verified.** `tsc --noEmit` exits 0; the full
   frontend suite passes (136 tests). **Playwright 1.64.0** is
   available for visual QA.
6. **Skill inspection (format/compatibility).** The UI/UX skills
   (`ui-ux-pro-max`, `impeccable`, `design-taste-frontend`,
   `design-system`) are present in the environment. They are
   *not* installed into the project and *not* invoked, because
   the standing constraint requires explicit user authorization
   before installing or using them.

**Exit criteria:** audit grounded in the real, building,
test-pinned application — met. The "install/activate skills"
and "define new visual direction" tasks are **held for user
authorization**; the existing design system is already
implemented, pinned, and conformant, so no unreviewed visual
change has been applied.

## Phase 6 — Premium Workstation Implementation ✅ (functional) / ⛔ (visual polish — gated)

**Status:** FUNCTIONAL COMPLETE — one integrated, functional
frontend with no broken primary workflows. Visual
"refine/polish" is gated on the same UI/UX-skill
authorization as Phase 5 (it would use those skills).

**Functional verification (this phase):**
- Full frontend suite: **136 tests passing across 12 files.**
- Every primary workflow has a dedicated, passing test:
  - flagship **Investigation** → `investigation-workspace.test.tsx`
  - **Falsification** → `falsification-matrix.test.tsx`
  - **Counterfactual Lab** → `counterfactual-lab.test.tsx`
  - **Command Center** → `command-center.test.tsx`
  - app shell + all routes → `app-shell.test.tsx`
  - shared components → `stitch-components.test.tsx`
  - design-system tokens → `design-system.test.ts`
  - ⌘K palette, universal question, workspace utilities
    → `command-palette.test.tsx`, `universal-question.test.tsx`
- `tsc --noEmit` exits 0 (type-safe).
- The 19 view components map 1:1 to the documented IA;
  no view is a stub or a broken workflow.

**Exit criteria met:** one integrated, functional frontend
with no broken primary workflows — verified by the passing
suite. The "refine/improve/enhance/polish" tasks are
visual refinements that require the authorized UI/UX
skills; they are held, and no unreviewed visual change
has been applied.

## Phase 7 — Production Hardening

**Status:** PENDING

**Goals:**
- Address security, reliability, persistence, performance, observability
- API contracts and operational recovery

**Key tasks:**
1. Add rate limiting
2. Implement authentication/authorization if needed
3. Add structured logging and tracing
4. Improve error handling and recovery
5. Performance optimization (bundle size, test suite runtime)
6. Security audit

**Exit criteria:** All applicable production gates pass or have explicitly documented blockers.

## Phase 8 — Final Verification and Release

**Status:** PENDING

**Goals:**
- Run full relevant tests, frozen intelligence benchmark, browser tests
- Visual audit and build
- Review diff and update documentation

**Key tasks:**
1. Run full test suite
2. Run frozen benchmark
3. Run browser tests if available
4. Visual audit
5. Build verification
6. Documentation update
7. Final report

**Exit criteria:** Reproducible verification evidence and an honest final report.

---

## Prioritization Principle

**Measure first. Improve the weakest critical capability. Verify the result. Preserve the system. Repeat.**

The weakest critical capabilities are:
1. Cross-race investigation (0/8) — a core reasoning capability
2. Qualifying investigations (0/5) — a data availability issue
3. Compound decomposition (3/14) — a core reasoning capability
4. Model integration — unexercised, blocking evaluation of LLM-dependent dimensions

These should be addressed in order of impact on the product's core mission: investigating F1 engineering problems.
