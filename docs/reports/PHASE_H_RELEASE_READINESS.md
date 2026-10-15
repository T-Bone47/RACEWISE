# Phase H — Release Readiness

## Decision: READY WITH DOCUMENTED LIMITATIONS

The bounded investigator is implemented, tested, and honest about its
bounds. Every Phase H requirement maps to either a verified pre-existing
capability or a newly implemented, tested one — nothing is claimed on
the basis of stubs.

## Requirement coverage

| Requirement | Status | Evidence |
|---|---|---|
| Bounded planner (budgets, deps, rationale) | pre-existing, verified | corpus 99.1%, planner tests |
| Plan validation gate | **implemented** | `validate_plan`, 22-test module |
| Model-plan validation | **implemented** | `validate_model_plan`, mocked tests |
| Bounded executor (states, timestamps) | **implemented** | execution ledger on every `ask()` |
| Retry classification | **implemented** | `_classify_error`; no-retry by construction, stated |
| Wall-clock budget | **implemented** | cooperative check, SKIPPED + reason |
| Per-tool thread timeouts | **documented limitation** | SQLite thread risk vs no observed need |
| Stopping reason | **implemented** | closed-vocabulary, derived from ledger |
| Evidence ledger integrity | pre-existing, verified | `_verify`, golden replay |
| Hypothesis lifecycle | pre-existing, verified | engine states + benchmark falsification case |
| Model-assisted planning | **implemented as validated helper** | mocked tests; deterministic dominance documented |
| Observability/replay | pre-existing, verified | `on_stage`, decision trace, replay tests |
| API/frontend integration | pre-existing (SSE, views) | unchanged this phase; 139/139 frontend (prior session) |

## Limitations (all measured)

1. Model planning cannot add executable value beyond deterministic
   planning (validated proposals ⊆ runnable set) — helper is advisory
   infrastructure, not an automatic path.
2. No per-tool thread timeouts (documented above).
3. Live-model behavior verified only for `openai/gpt-oss-20b`; 8 catalog
   models unverified; no cost data.
4. Elliptical follow-up fragments don't compile (carried over from
   Phase G; recommended next milestone stands).

## Regression risks

- Planner additions flow through the existing budget trim; corpus
  steady; golden path file-isolated (verified by import graph).
- Synthesizer guard adds `not_established` entries only; no status
  logic touched.
- `resolve_task` changes a dormant failure into working code paths;
  covered by new tests + all existing prompt/registry tests.

## Recommended next milestone

**Elliptical follow-up understanding** (unchanged from Phase G):
compiling scope-carrying fragments against inherited context. The
bounded executor + stopping reason built this phase make the failure
mode observable; the missing piece is intake-level fragment resolution.
