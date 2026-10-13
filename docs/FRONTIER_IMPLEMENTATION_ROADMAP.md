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

## Phase 1 — Intelligence Evaluation Foundation

**Status:** PENDING

**Goals:**
- Strengthen the versioned benchmark with deterministic scoring
- Create a holdout evaluation set (15% of corpus, race-grouped)
- Define failure taxonomy from existing 87 failing cases
- Build reproducible evaluation report generation

**Key tasks:**
1. Analyze the 87 failing corpus cases and categorize failures
2. Create `tests/benchmark/holdout/` with race-grouped holdout set
3. Implement deterministic scoring for each evaluation dimension
4. Create `docs/FRONTIER_EVALUATION_PROTOCOL.md` (this document)
5. Build evaluation report generator that outputs before/after metrics

**Exit criteria:** The existing system can be measured before and after changes with reproducible results.

## Phase 2 — Core Investigation Quality

**Status:** PENDING

**Goals:**
- Improve question engine pass rate from 62.2% to ≥75%
- Fix cross-race (0/8) and qualifying (0/5) categories
- Improve compound decomposition (3/14 → ≥8/14)
- Strengthen falsification and abstention behavior

**Key tasks:**
1. Fix cross-race capability selection in planner
2. Wire qualifying code path to planner capability selection
3. Improve compound decomposition reach
4. Add stint category support
5. Strengthen falsification tests
6. Improve abstention calibration

**Exit criteria:** Demonstrable improvement without regressions in frozen evaluation set.

## Phase 3 — Model Tuning Decision

**Status:** PENDING

**Goals:**
- Compare controlled prompt/orchestration changes
- Determine whether fine-tuning is justified
- Prepare training pipeline only if data/access/evaluation requirements are satisfied

**Key tasks:**
1. Audit provider abstraction and prompt templates
2. Test targeted prompt improvements (one factor at a time)
3. If multiple models available, compare on same benchmark
4. Document fine-tuning decision with evidence

**Exit criteria:** Documented, evidence-backed model strategy. Fine-tuning is optional and must not be falsely claimed.

## Phase 4 — Integration and Specialist-Tool Boundaries

**Status:** PENDING

**Goals:**
- Verify LFI evidence_v1 integration
- Inspect whether simulator integration is justified
- Preserve separate repositories and authoritative calculation ownership

**Key tasks:**
1. Audit LFI evidence_v1 contract and runtime
2. Test evidence_v1 schema compliance
3. Evaluate simulator integration feasibility
4. Document integration contracts

**Exit criteria:** Tested contracts and no blind duplication or semantic drift.

## Phase 5 — Design System and UI/UX Audit

**Status:** PENDING

**Goals:**
- Inspect existing frontend against design system
- Install or activate authorized skills
- Extract and document design system
- Define new visual direction

**Key tasks:**
1. Audit existing UI against DESIGN.md and RACEWISE_DESIGN_SYSTEM.md
2. Install/verify UI/UX skills (ui-ux-pro-max, impeccable, taste)
3. Run visual QA with Playwright if available
4. Document design system refinements

**Exit criteria:** Approved implementation plan grounded in the real application.

## Phase 6 — Premium Workstation Implementation

**Status:** PENDING

**Goals:**
- Refine application shell, active investigation, hypotheses, evidence workbench
- Counterfactual lab, report, provenance, replay views
- One integrated, functional frontend with no broken primary workflows

**Key tasks:**
1. Refine flagship investigation workspace
2. Improve hypothesis workspace
3. Enhance evidence workbench
4. Polish counterfactual laboratory
5. Improve investigation report
6. Enhance memory, comparison, and replay views

**Exit criteria:** One integrated, functional frontend with no broken primary workflows.

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
