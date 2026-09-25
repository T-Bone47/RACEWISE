# PHASE 6N — ENGINEERING INVESTIGATION SYNTHESIS & DECISION TRACE

Methodology reference for `run_engineering_investigation` (MCP) and
`GET /api/catalog/engineering-investigation`. Companion report:
`PHASE_6N_COMPLETION_REPORT.md`.

## 1. Mission

Phase 6M answers: *across recurring patterns, how does evidence behave?*
Phase 6N answers the orchestration question above the entire verified chain:

> Given a specific engineering question, what evidence supports each
> competing hypothesis, what evidence contradicts it, what remains
> untestable, and which bounded counterfactuals can actually be executed?

6N makes RACEWISE **more traceable, not more opinionated**: deterministic
evidence → structured evaluation → evidence-bound synthesis, with a decision
trace from every conclusion to concrete evidence IDs.

## 2. Architecture

6N sits **above** 6M and consumes the verified layers verbatim — it
duplicates no calculation:

```
6E attribution → 6F fusion → 6G stints → 6H race gap → 6I counterfactuals
→ 6J envelope → 6K regimes → 6L patterns → 6M evidence
→ 6N INVESTIGATION ORCHESTRATION (question → plan → ledger → evaluation
   → falsification gate → counterfactual eligibility → synthesis → trace)
```

Module: `src/racewise/data/historical/investigation_synthesis.py`
(`6n_investigation_v1`). The legacy LLM-driven investigation engine
(`src/racewise/investigation/engine.py`) is **not invoked** and was not
modified; its session machinery is untouched at `POST /api/investigations`.

## 3. Question framing

Closed vocabulary (no free-form logic exists):

```
LAP_PERFORMANCE  STINT_PERFORMANCE  RACE_GAP  PERFORMANCE_REGIME
CROSS_RACE_PATTERN  HYPOTHESIS_EVALUATION  COUNTERFACTUAL_ELIGIBILITY
```

Framing validates, in order: question type membership; driver presence and
distinctness; season bounds `[1950, 2100]`; round bounds `[1, 99]`;
lap/stint positivity and mutual exclusivity; per-type required parameters
(lap for LAP/HYPOTHESIS types, stint for STINT, pattern_id for
CROSS_RACE_PATTERN). Then data-derived checks: the race result must exist
(else `UNAVAILABLE`), both drivers must appear in it, a requested lap must
exist in canonical lap times, a requested stint must exist in canonical
stints. The request is never silently broadened. States: `VALID`,
`INVALID`, `UNAVAILABLE`.

## 4. Hypotheses

The six canonical 6F hypothesis IDs are reused verbatim: `H1_corner_speed`,
`H2_throttle`, `H3_braking`, `H4_tyre_state`, `H5_race_control`, `H6_drs`.
An optional `hypotheses` subset marks excluded hypotheses `NOT_REQUESTED` —
excluded ≠ unsupported, and no hypothesis is ever silently removed.

## 5. Evidence planning

`QUESTION_EVIDENCE_PLAN` maps each question type to the existing analytical
tools only (6E `attribute_lap_loss`, 6F `fuse_lap_evidence`, 6G
`fuse_stint_evidence`, 6H `decompose_race_gap`, 6I counterfactual paths, 6K
`analyze_performance_regimes`, 6L `analyze_cross_race_performance_patterns`,
6M `analyze_cross_race_pattern_evidence`). The planner invents no tool.

## 6. Evidence ledger

Each item carries: `evidence_id`, `evidence_type` (FACT / CALCULATION /
INFERENCE / COUNTERFACTUAL — the existing taxonomy), `source_phase`,
`source_tool`, `source_reference`, `source_hash` (sha256[:16] of the
reference), `claim`, `claim_class` (OBSERVED / DERIVED / INFERRED /
MODELLED — structural, never merged), `measured_value`, `units`, `state`,
`hypothesis_ids`, `assumptions`, `limitations`, `supports`, `contradicts`.
Bound: `max_evidence_items` ≤ 40.

## 7. Hypothesis evaluation

Per hypothesis: supporting / contradicting / non-decisive evidence ID lists,
`evidence_coverage` counts, one aggregate state, `falsification_status`,
`unresolved_contradictions`. Aggregate states: `SUPPORTED`,
`PARTIALLY_SUPPORTED`, `NOT_SUPPORTED`, `CONTRADICTED`, `NOT_TESTABLE`,
`INSUFFICIENT_EVIDENCE`, `MIXED_EVIDENCE` (+ `NOT_REQUESTED`). No scores,
no ranking, no winner.

## 8. Falsification gate

Direct conflict pairs (support ∧ contradict on a shared hypothesis) produce
`MIXED_EVIDENCE` with `falsification_status = MIXED` and
`unresolved_contradictions = true`. The gate blocks every hypothesis with
unresolved contradictions from `establishable_hypotheses`: **a hypothesis
with unresolved contradictions cannot be synthesized as an established
explanation.** Conflicts are preserved in `evidence_conflicts` with
`DIRECT_CONTRADICTION` / `UNRESOLVED` — never resolved away.

## 9–10. Counterfactual eligibility and execution

Nothing executes before eligibility. Candidates are checked with the exact
6I extraction path (`extract_speed_profile` probe on target laps; stint
probes use 6G `selected_laps`, bounded at 3 probe / 2 collect laps):

| state | meaning |
|---|---|
| `ELIGIBLE` | 6I speed-profile model covers the scope |
| `INELIGIBLE` | race-level telemetry extrapolation — structurally ineligible |
| `UNSUPPORTED_MODEL` | non-speed signal (6I models `speed` only) |
| `TELEMETRY_UNAVAILABLE` | no extractable paired speed profile |
| `INSUFFICIENT_EVIDENCE` | stint has no selectable comparable laps |

Only `ELIGIBLE` candidates execute — through the untouched 6I simulators
(`simulate_telemetry_counterfactual` / `simulate_stint_counterfactual`),
bounded at `max_counterfactuals` ≤ 2. Executed results enter the ledger as
`COUNTERFACTUAL` / `MODELLED` items: *the model is sensitive to the
specified intervention* — never historical causality, never prediction.

## 11. Synthesis

Conclusion states (closed): `SUPPORTED_BY_AVAILABLE_EVIDENCE`,
`MIXED_EVIDENCE`, `INSUFFICIENT_EVIDENCE`, `NOT_TESTABLE`, `UNAVAILABLE`.
`BEST_EXPLANATION` / `MOST_LIKELY_CAUSE` / `WINNER` do not exist. Facts are
stated only with provenance; derived statements name their method;
unavailable evidence is listed, never interpreted as negative evidence; if
no hypothesis is establishable the conclusion is honest
(`INSUFFICIENT_EVIDENCE` / `MIXED_EVIDENCE` / `UNAVAILABLE`).

## 12. Decision trace

Every synthesis statement is a trace entry `TRACE-nnn` with `statement`,
`basis` (evidence IDs ⊆ ledger), `type`, `supporting_hypotheses`,
`contradictory_evidence`, `status`. No statement exists without traceable
evidence. The frontend makes each entry expandable down to source phase,
tool, source hash, measured value and limitations.

## 13. Replay & determinism

Output is canonical (sorted keys, compact separators, `default=str` via the
shared `_hash_obj`). No timestamps, no process IDs, no random IDs;
`investigation_id` is derived from the question scope. Verified: in-process
repeat byte-identical, subprocess replays identical under
`PYTHONHASHSEED=3` and `PYTHONHASHSEED=29`, MCP wire repeat identical
(`duration_ms` excluded), API repeat byte-identical.

## 14. Provenance & snapshot

`provenance.analytical_chain` is the full `6E → … → 6N` chain; the snapshot
records input, evidence IDs, per-evidence source hashes, hypothesis states
and counterfactual IDs. Provenance is `source_tool` + `source_phase` +
`source_hash` + tables — never "AI analysis says".

## 15. Security

Closed enums, mandatory bounds, unknown-parameter rejection at the tool
contract (closed via the input schema `properties`), distinct-driver
validation, no eval/exec/shell/SQL from user input, read-only DB
(derived-on-read; the DB file is untouched — asserted by test), no dynamic
tool invocation. Host-agent text can never become executable logic.

## 16. Storage

Zero storage growth. Investigations are derived on read; no tables, files or
caches are written. Verified by byte-size/mtime comparison before/after.

## 17. Performance

Measured in Q16 (`elapsed_ms` per golden, p50/p95/max in the report):
lap/stint/race-gap investigations run in ~0.1–5 s; cross-race pattern
investigations dominate (~58 s incl. the discovery scan) because 6L scans
the corpus — documented, not hidden. Collection memoizes layer results
within one invocation; the same layer is never executed twice for the same
scope.

## 18. Limitations

- GOLDEN_06 resolves to a real 6L pattern whose 6M evidence is non-recurring
  at the collector's default scope → honest `INSUFFICIENT_EVIDENCE` with the
  6L fact retained in the ledger.
- RACE_GAP / PERFORMANCE_REGIME investigations on the current corpus are
  evidence-sparse and end `INSUFFICIENT_EVIDENCE` (honest, per contract).
- Counterfactuals remain lap/stint speed-profile only (6I scope).
- The legacy LLM investigation endpoint remains for the host-driven flow;
  6N shares no state with it.
