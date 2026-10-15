# Phase H — Autonomous Investigator

## Reconnaissance (§1): what already existed

Verified by inspection before any edit (no duplication introduced):

| Phase H requirement | Pre-existing implementation | Verdict |
|---|---|---|
| Bounded planner, budgets | `planner.build_plan` + `DEFAULT_BUDGET`, testability gates, deferred reporting | complete; extended, not replaced |
| Cancellation | `engine.RUNS` registry, checkpoints, supersession | complete |
| Evidence ledger | answer `evidence_ledger`, 6N ledger with source hashes, `_verify` | complete |
| Hypothesis lifecycle | engine states, supporting/contradicting buckets | complete |
| Stopping | answer statuses + `not_established`/`missing_evidence` | partial → explicit `stopping_reason` added |
| Model planning helper | `INVESTIGATION_PLANNING` template (unwired) | gap → `propose_plan_with_model` added |
| Plan validation gate | implicit only | gap → `validate_plan`/`validate_model_plan` added |
| Per-step execution records | results/errors dicts only | gap → execution ledger added |
| Observability/replay | `on_stage` callbacks, decision trace, `InvestigationEngine.replay`, 6N replay tests | complete |
| SSE streaming | `StreamingResponse` investigation endpoints | complete (unchanged) |

## Implemented changes and rationale

1. **Plan validation** (`planner.validate_plan`, `validate_model_plan`):
   duplicates, unknown tools, cycles, malformed/budget violations.
   Prerequisite-closure membership deliberately NOT required: capabilities
   execute standalone with explicit arguments (verified in
   `_execute_capabilities`), so composition is conceptual. A stricter rule
   was tried, failed against the real Perez plan, investigated, and
   corrected — the validator now encodes the true architecture.
2. **Execution ledger + stopping reason** (`engine._execute_capabilities`,
   `ask`): per-capability SUCCEEDED/FAILED/SKIPPED with duration,
   error class, retry_count=0 (deterministic tools cannot usefully retry;
   stated once in `_classify_error`). Wall-clock budget enforced
   cooperatively between steps (120 s default, matching 6T). Response
   carries `execution` + `stopping_reason` (derived, never prose).
   Per-tool thread timeouts deliberately NOT implemented: SQLite-backed
   tools are sample-capped and fast; thread timeouts risk correctness
   for no observed need (documented limitation).
3. **Task-name resolution fix** (`prompt_templates.resolve_task`): bare
   `PromptTask("NAME")` raised ValueError, which made
   `generate_with_template` fail for EVERY string task — a dormant
   defect (only reachable with a live provider). Fixed + tested,
   including the same latent bug in `PromptRegistry.get` pinned versions.
4. **Model-assisted planning** (`planner.propose_plan_with_model`):
   validated helper; numbering the honest finding — a validated model
   plan can only reorder/subset runnable capabilities, so deterministic
   planning dominates execution. Documented in the docstring, not wired
   into any automatic path (wiring a no-op would be theatre).
5. **Planner scope completion + corner guard + stint repair** (Phase G
   work, same commit): sector/baseline capability completion,
   corner-level-attribution limitation, dead `analyze_stint` branch
   restored via shared `default_common_stint()`.

## Investigation lifecycle (as built)

`COMPILE → PLAN (validate) → INVESTIGATE (ledger, budget) → AUTOPSY →
SYNTHESIZE → VERIFY → answer`, with `stopping_reason` and `execution`
on every response, `on_stage` callbacks for progress, cancellation
checkpoints, and deterministic fallback at every model touchpoint.
Hypotheses: engine states only; a SUPPORTED state requires evidence +
tests, never model agreement. Stopping reasons are closed vocabulary
derived from the ledger (all-executed / errors / skipped / unplannable).
