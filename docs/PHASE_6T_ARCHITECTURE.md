# PHASE 6T ARCHITECTURE — AUTONOMOUS ENGINEERING INVESTIGATION

Status: design-first document (mandated by Phase 6T §2 before major
implementation). This document describes the orchestration layer that
Phase 6T adds **around** the existing deterministic engineering engine. It
invents no new analytical capability and creates no parallel investigation
framework.

---

## 0. What Phase 6T is — and is not

RACEWISE already answers engineering questions deterministically
(Phases 6E→6S: attribution, evidence fusion, stint/race-gap/regime/pattern
evidence, bounded counterfactuals, 6N investigation synthesis, 6O memory,
6P graph, 6Q command center, 6R/6S validation). What it lacks is a layer
that takes a **natural-language engineering question** and autonomously
drives the existing machinery from question to replayable, provenance-bound
answer — or stops honestly when the data does not support one.

Phase 6T adds exactly that: a **deterministic autonomous orchestration
layer**. "Autonomous" means the layer selects tools, sequences evidence
collection, adapts to what evidence exists, and decides when to stop —
without a human steering each call. "Deterministic" means every one of
those decisions is a pure function of declared inputs (question text,
canonical context, catalog facts, prior tool results) with a fixed policy
version, recorded in a decision trace, and replayable.

**Not Phase 6T:** an LLM in the calculation path. No telemetry deltas,
hypothesis states, counterfactuals, or provenance are ever produced or
modified by a language model. The LLM boundary is §8 of this document and
`docs/PHASE_6T_SECURITY_MODEL.md`.

---

## 1. Non-negotiable architectural rules

1. **The deterministic engine remains the only authority.** Data,
   calculations, evidence, hypothesis states, counterfactuals, provenance
   and replay are produced exclusively by the existing Phase 6E→6S chain
   (`investigation_synthesis.py` and the modules it calls). The
   orchestrator may choose *whether/when* to invoke them, never *what they
   return*.
2. **No second analytics engine.** The orchestrator wraps
   `run_engineering_investigation` (6N); it never re-implements evidence
   fusion, attribution, or any layer beneath 6N. Evidence deduplication
   across branches is achieved by *routing through the 6N engine once per
   distinct scope* and reusing its evidence ledger — identity by content
   hash.
3. **Closed vocabularies everywhere.** Question types, session types,
   hypothesis ids, lifecycle states, decision types, failure reasons —
   all closed tuples, validated on entry. Nothing free-form crosses the
   engine boundary.
4. **Honesty over completeness.** Every stop that is not `COMPLETED`
   carries a closed-vocabulary failure state and a human-readable,
   evidence-referenced reason. Failures are never hidden, and a failure
   state is never silently converted into a weaker success.
5. **Derived-on-read, additive storage.** The 6N engine is derived-on-read
   with zero storage growth; 6T keeps that property for investigation
   results. The only persisted artifacts are autonomous **run records**
   (bounded, append-only, see §6) and 6O memory items (existing rules).
6. **The user's question text is data, never instruction** (§8, and
   Phase 6T §34 of the mandate).

---

## 2. Module placement

```
src/racewise/data/historical/
    question_intake.py          NEW  — NL question → canonical question
                                      object (deterministic parsing +
                                      optional LLM assist, §8)
    autonomous_investigator.py  NEW  — lifecycle state machine, evidence
                                      planning, adaptive collection,
                                      budgets, decision trace, synthesis
                                      wrap, replay, follow-ups
src/racewise/api/app.py          EXT  — /api/investigations/autonomous*
apps/web/src/AutonomousView.tsx  NEW  — autonomous workspace (§26/27/28)
```

Why under `data/historical`: every capability the orchestrator drives lives
there today (6N/6O/6P are `data.historical`); the orchestrator is a peer
consumer of `CanonicalQueries`, not a new framework. The legacy
`investigation/` engine + `persistence/` store (LLM-era, `POST
/api/investigations`) remain untouched; 6T shares no state with them and
the provenance of every autonomous result records that the legacy engine is
not invoked.

`investigation_id` semantics are **preserved**: a 6T run over a scope that
reaches COMPLETED embeds the 6N `investigation_id` (content hash of the
canonical question + pair) unchanged — replay, graph, memory, deep links
and goldens all key on it exactly as 6R/6S built them.

---

## 3. Canonical question object

Produced by `question_intake.parse_question`; every field is either
resolved from canonical data or absent (never guessed).

```json
{
  "question_text": "Why did Verstappen lose time to Perez in Bahrain 2023?",
  "question_type": "LAP_PERFORMANCE | STINT_PERFORMANCE | RACE_GAP | PERFORMANCE_REGIME | CROSS_RACE_PATTERN | HYPOTHESIS_EVALUATION | COUNTERFACTUAL_ELIGIBILITY | QUALIFYING_LAP_PERFORMANCE",
  "season": 2023,
  "round": 1,
  "session_type": "RACE",
  "driver_a": "max-verstappen",
  "driver_b": "sergio-perez",
  "lap_number": 6,
  "stint_number": null,
  "pattern_id": null,
  "hypotheses": null,
  "constraints": {"max_tool_calls": 60, "max_cross_race_scans": 2},
  "provenance": {
    "method": "deterministic_regex_intake_v1",
    "resolution_log": [ {"kind": "DRIVER", "text": "Verstappen",
                          "resolved": "max-verstappen", "source": "canonical_drivers"} ]
  }
}
```

Notes:
- `QUALIFYING_LAP_PERFORMANCE` is **not** a new engine question type: the
  intake emits `LAP_PERFORMANCE` + `session_type=QUALIFYING` (Phase 6S
  semantics). It appears in the intake vocabulary so NL questions about
  qualifying parse honestly.
- Drivers are resolved to canonical `driver_key` slugs via exact code /
  full-name matching over `canonical_drivers`; **no fuzzy mapping**. If a
  name cannot be resolved to exactly one canonical driver, the field is
  absent and the question stays `CONTEXT_UNRESOLVED` (the API responds
  409 with the open text and, where a season is known, the participant
  list — "ask for clarification", never silently choose).
- The well-known counter-example is a first-class test: "Kimi Antonelli"
  **in a 2023 race** resolves to a canonical driver whose key exists but
  who is not a participant of that race → the 6N scope check returns
  UNAVAILABLE, and 6T surfaces it as a failure state with the reason —
  never a substitution.

---

## 4. Lifecycle state machine

The mandate's canonical states, in one machine
(`autonomous_investigator.LIFECYCLE`):

```
CREATED → QUESTION_PARSED → CONTEXT_RESOLVED → DATA_CHECKED →
HYPOTHESES_SELECTED → EVIDENCE_PLANNED → EVIDENCE_COLLECTING →
HYPOTHESES_EVALUATED → FALSIFICATION → COUNTERFACTUAL_CHECK →
SYNTHESIS → VERIFICATION → COMPLETED
```

Failure states (terminal, closed):
`INVALID_QUESTION`, `CONTEXT_UNRESOLVED`, `DATA_UNAVAILABLE`,
`INSUFFICIENT_EVIDENCE`, `TOOL_FAILURE`, `MODEL_FAILURE`,
`VERIFICATION_FAILURE`, plus `BUDGET_EXHAUSTED` and
`UNSUPPORTED_QUESTION`.

Rules:
- One stage transition = one decision-trace entry (§7). The stage ledger is
  the machine; nothing else tracks progress.
- `DATA_CHECKED` is a real gate: per-facet availability comes from the
  catalog (`canonical_session_catalog` availability columns, the same
  source `get_availability` reads). Required facets for the question type
  map to AVAILABLE / PARTIAL / UNAVAILABLE; a required-unavailable facet
  ends the run in `DATA_UNAVAILABLE` **before** any expensive tool runs.
- `INSUFFICIENT_EVIDENCE` and `TOOL_FAILURE` are also reachable mid-run
  from collection results; `BUDGET_EXHAUSTED` fires when a budget
  dimension hits its bound mid-plan (never mid-tool).
- `UNSUPPORTED_QUESTION` is produced at `QUESTION_PARSED` when the text
  expresses an engineering intent outside the closed vocabulary (e.g.
  "which chassis is fastest", predictions, betting-style questions) —
  with an explanation naming the supported question types.

`EVIDENCE_COLLECTING` wraps the 6N engine, which executes the phase layers
(6E→6M) per its own plan. Adaptive behavior (§10 of the mandate) is
implemented as: **plan → collect → inspect → re-collect** loop at the
planning level (e.g. stint→lap refinement via the 6N stint probe budget),
driven by evidence-identity checks, with every loop decision traced.
Within a single 6N execution the engine's own established adaptive
semantics hold (status-aware layers, honest INSUFFICIENT outcomes).

---

## 5. Evidence planning and adaptive collection

The evidence plan is the existing `QUESTION_EVIDENCE_PLAN` (6N) annotated
with the orchestrator's *adaptive* expectations — the deterministic layer
already executes it; 6T makes the plan explicit and the adaptation
auditable:

- Planned items map 1:1 to real deterministic tools (never an imaginary
  source); each planned item records `why_planned`.
- Collection loop: run planned tool → inspect status → if the status
  reveals a cheaper or missing prerequisite (e.g. telemetry
  unavailable ⇒ telemetry-dependent hypotheses are NOT_TESTABLE, sectors
  still decidable) the loop continues with remaining plan items but
  **never** re-queues a structurally-impossible tool. Repeats of an
  already-satisfied evidence identity are skipped (dedup by evidence id /
  source hash).
- If evidence contradicts the working reading (6N reports
  DIRECT_CONTRADICTION), the run records a `REQUEST_MORE_EVIDENCE`
  decision and consults the remaining plan layers before synthesizing.
- Residual (unassigned measured delta) is preserved as unresolved
  evidence; the orchestrator never assigns it.

---

## 6. Budgets

Closed budget dimensions, defaulted by policy (overridable within bounds
via `constraints`), exposed in every response as `{budget, consumed,
remaining}`:

- `max_tool_calls` (default 60) — counts deterministic tool invocations
  performed on behalf of the run, including the embedded 6N execution
  counted per its executed analytical layers.
- `max_runtime_ms` (default 120000) — checked between stages/tools, never
  interrupts a running deterministic tool (integrity over latency).
- `max_counterfactuals` (default 2, engine bound) — passes through to 6N.
- `max_cross_race_scans` (default 2) — bounds pattern discovery scans for
  CROSS_RACE_PATTERN questions.
- `max_memory_neighbors` (default 1, bound ±1 season — Phase 6S pool) —
  bounds related-memory expansion.

Budget exhaustion ends the run `BUDGET_EXHAUSTED` with the dimension, the
bound and what was about to run. Every consumption entry carries
provenance (which decision consumed it). Runs are checkpointed: the run
record stores the completed stages, the plan, the budget ledger and the
decision trace, so a `continue` call resumes at the exact next stage
(deterministically re-deriving rather than re-paying expensive work where
the record already holds a valid result).

---

## 7. Decision trace

Every autonomous decision appends one entry (closed `decision_type`
vocabulary):

```
PARSE_QUESTION | RESOLVE_CONTEXT | CHECK_DATA | SELECT_HYPOTHESES |
PLAN_EVIDENCE | SELECT_TOOL | SKIP_TOOL | REQUEST_MORE_EVIDENCE |
RUN_COUNTERFACTUAL | STOP_INVESTIGATION | SYNTHESIZE | VERIFY
```

Entry shape: `{decision_id, order, decision_type, input_state, reason,
selected_action, tool, tool_result_hash, evidence_refs, output_state}`.
The trace is carried in the result and persisted in the run record.
Orchestration reasons are clearly labelled `ORCHESTRATOR:` while engine
statements carry their own existing trace — the §28 boundary ("orchestrator
selected braking analysis…" vs "engine: Braking hypothesis CONTRADICTED")
is enforced in the data model, not just the UI.

---

## 8. LLM boundary (Union Alpha / optional)

The existing `agent/provider.py` protocol stays. 6T uses a provider, when
one is configured, for **one thing only**: assistance in interpreting free
text at intake (§3). Its output is canonicalized into the deterministic
question schema and every extracted value is verified against canonical
data before use; anything unverifiable is dropped. With no provider
configured (the default), the deterministic parser handles the same
vocabulary — the deterministic path is the contract, the LLM path is an
optional accelerator with identical output schema, and both record their
method in provenance.

LLM may never: calculate, invent evidence, assign hypothesis states,
fabricate provenance, modify numerical output, or override deterministic
results. The deterministic engine wins every disagreement by construction
(the orchestrator never reads LLM output after `QUESTION_PARSED`).
Prompt-injection resistance (§34 of the mandate) is enforced at this
boundary: question text is quarantined as data, strategy-pattern
instructions inside it are recorded in the run record, and the
deterministic pipeline never treats them as directives.

---

## 9. Synthesis, answer format, follow-ups

The engine's 6N synthesis (evidence-grounded, closed conclusion states,
epistemic boundaries) is embedded verbatim under the canonical answer
object:

```json
{
  "investigation_id", "run_id", "question", "context",
  "lifecycle", "stage_ledger", "decision_trace",
  "executive_summary", "findings", "hypotheses", "contradictions",
  "counterfactuals", "unresolved_questions", "limitations",
  "evidence_refs", "provenance", "plan", "budget", "replay", "graph"
}
```

- Every finding references evidence ids; every numerical claim references
  a deterministic output (hash-bound); claim classes OBSERVED / DERIVED /
  INFERRED / MODELLED are propagated from the engine — the orchestrator
  adds none of its own.
- Executive summary language: "evidence supports…" only; causation words
  appear only where the underlying methodology establishes them (6N
  already enforces this; 6T adds no prose of its own beyond template text
  over engine fields).
- Follow-up questions are derived from actual missing evidence only:
  insufficient hypothesis evidence → the specific bounded next probe;
  unavailable facet → its name; residual → the pattern question that
  would test recurrence. Generic suggestions are structurally impossible
  (every follow-up cites the evidence id / scope fact that motivates it).

---

## 10. Memory, graph, replay

- **Memory** — completed runs derive 6O memory via the existing
  `derive_memory_items` (exact layer) and may attach structural related
  memory via `retrieve_related_engineering_memory` (Phase 6S rules,
  bounded by `max_memory_neighbors`). Related memory remains **pointers,
  not conclusions**; nothing about 6T changes transfer policy.
- **Graph** — completed runs are graphable by the unchanged
  `build_investigation_graph` (6P) via the 6N result; the run's decision
  trace is attached as run metadata, not as fabricated graph nodes. No
  causal edges beyond what the engine already declares.
- **Replay** — `replay_autonomous_investigation` re-executes from the run
  record: parses the recorded question text, re-derives the plan, re-runs
  the 6N engine, and compares stage ledger, decision trace, evidence ids,
  hypothesis states, synthesis and output hash. IDENTICAL / CHANGED with
  explicit changed evidence (6O replay semantics, reused). Replay of a
  failed run reproduces the failure state.

---

## 11. API surface

```
POST /api/investigations/autonomous            {question, context?, constraints?}
GET  /api/investigations/autonomous/{run_id}
POST /api/investigations/autonomous/{run_id}/continue
POST /api/investigations/autonomous/{run_id}/replay
GET  /api/investigations/autonomous/{run_id}/stream    (SSE, real stages)
```

- Extends, does not duplicate: the canonical result embeds the 6N
  investigation id; `/continue` resumes an interrupted/budgeted run;
  `/replay` reuses 6O replay semantics on the autonomous snapshot.
- Streaming is real: the SSE endpoint drives the same state machine
  in-process and emits actual stage transitions (no timers, no simulated
  progress). The synchronous POST runs the same machine to completion.
- Failure states map to HTTP: 422 (invalid question / malformed
  constraints), 404 (unknown run), 409 (context unresolved — with the
  clarification payload), 200-with-status for honest in-band outcomes
  (data unavailable, insufficient evidence, budget exhausted — these are
  *results*, not transport errors).

---

## 12. Frontend — autonomous workspace

New `#autonomous` view (InvestigationView and all 17 existing views stay
untouched): question input, optional structured context (season/round/
session/driver A/driver B), START INVESTIGATION, then live stage timeline
(SSE), hypothesis panel with states, evidence ledger, contradiction
section, counterfactual section, synthesis, provenance inspector, decision
trace, replay button, graph deep link, memory section. Orchestration
decisions and engine results are visually distinct (§28), the same
workspace primitives as 6Q (StateChip, KV, Drawer) reused. Follow-up
suggestions render as clickable chips that start the corresponding
structured investigation.

---

## 13. Testing and acceptance (mapping to the mandate)

- **Corpus** `tests/benchmarks/phase_6t_autonomous_investigations.json` —
  30+ NL questions over real contexts (10 lap, 5 stint, 4 qualifying,
  4 race gap, 3 regime, 2 cross-race, 2 counterfactual) plus limitation
  cases: unknown driver, missing telemetry, insufficient evidence,
  contradiction, unsupported question, budget exhaustion.
- **Adversarial tests** — wrong driver/season/future data/unknown race/
  missing session, malformed context, budget zero, tool failure,
  prompt-injection strings, instruction-override attempts, replayed
  changed data. Determinism: same process ×3, fresh process,
  PYTHONHASHSEED 3/29.
- **No-fabrication scan** — every finding/claim in every corpus result is
  checked for an evidence reference and a source hash; free text fields
  must cite deterministic outputs.
- **Goldens** — 10+ autonomous goldens (contradiction ×3, limitation ×2,
  counterfactual ×2, qualifying ×2, cross-race ×1 at minimum), each with
  plan hash / investigation id / output hash / snapshot hash / replay
  hash / provenance hash / graph hash, appended to the 6R golden file
  convention (`phase_6t` golden ids).
- **Regression** — all 737+ existing tests, 6R 72-case benchmark,
  MCP/API/frontend suites; 6T adds its benchmark without touching 6R
  assets. Performance measured (p50/p95/max per stage) and reported.
- **E2E** — real-browser pass over the full workspace flow.

## 14. Known limitations carried into 6T

- The deterministic intake parser covers a closed, documented phrasing
  vocabulary; outside it, questions are `UNSUPPORTED_QUESTION` or
  `CONTEXT_UNRESOLVED` (honest), never guessed.
- Orchestration is sequential (no parallel tool execution); budget and
  performance bounds account for this.
- Related memory and pattern discovery are bounded (±1 season pool;
  `max_cross_race_scans`) — depth-for-latency trades are explicit.
- The legacy LLM-era engine (`investigation/`, `POST /api/investigations`)
  is out of 6T scope; it remains available but unused by the autonomous
  layer.
