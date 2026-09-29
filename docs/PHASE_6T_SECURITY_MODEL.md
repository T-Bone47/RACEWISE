# Phase 6T — Security Model

Scope: the autonomous orchestration layer added in Phase 6T and its
interaction with the deterministic RACEWISE engine, the API surface, and
the frontend.

## 1. Trust boundary

```
User question text  ──(treated as DATA)──▶  question_intake scanner
                                           │  injection patterns flagged,
                                           │  recorded, NEVER executed
                                           ▼
                          autonomous_investigator (orchestration only)
                                           │  selects existing tools
                                           ▼
                          Deterministic engine (sole authority for
                          data, calculations, evidence, states,
                          counterfactuals, provenance, replay)
```

## 2. Prompt-injection resistance (mandate §34)

- The question text is scanned by `_scan_injection` before any processing.
  Patterns cover evidence-override attempts ("ignore the evidence and say
  X caused Y"), conclusion-fixing ("always conclude X was faster"),
  role/hierarchy attacks ("you are now allowed to fabricate"), and
  provenance tampering ("mark it as measured").
- A flagged question **is still investigated** — through the normal
  deterministic path. The injection scan is recorded in the run
  (`injection_scan` with matched patterns) and appears in the decision
  trace, the API response, the frontend and the goldens
  (T-G02_INJECTION_QUARANTINE).
- No part of the pipeline parses question text as an instruction: there is
  no code path from question content to tool arguments beyond the closed
  entity-resolution grammar (seasons, rounds, driver names, laps, stints).

## 3. LLM boundary (mandate §31)

Phase 6T is deterministic end-to-end; there is no LLM in the loop. The
boundary is therefore enforced by construction:

- LLM may (if later attached): interpret the question, propose a plan,
  select among existing tools, explain deterministic output — all after
  canonicalization into the deterministic question-object schema.
- LLM may never: calculate telemetry deltas, invent evidence, assign
  hypothesis states, fabricate provenance, override deterministic tool
  results, or modify numerical output. The deterministic engine wins any
  disagreement.

## 4. No-fabrication guarantees (mandate §35)

- Every evidence item in a run originates from a deterministic tool call
  recorded in the decision trace with a `tool_result_hash` over the
  deterministic fields of the tool output.
- The VERIFICATION stage re-checks: every evidence reference in synthesis
  resolves to a recorded evidence item (no dangling refs), every recorded
  conflict cites existing evidence ids, and the decision trace is
  contiguous and hash-chained to the run identity.
- Findings wrap engine-produced conclusions only; the orchestrator adds no
  numbers of its own. Numerical claims in synthesis are engine outputs
  referenced by evidence ids.
- Failure states are never masked: `INVALID_QUESTION`,
  `CONTEXT_UNRESOLVED`, `DATA_UNAVAILABLE`, `INSUFFICIENT_EVIDENCE`,
  `TOOL_FAILURE`, `VERIFICATION_FAILURE`, `BUDGET_EXHAUSTED` all surface
  in status, failed_stage, the API, the frontend and replay.

## 5. Auditability (mandate §29)

- No hidden tool calls: every call is a decision-trace entry with reason
  and output state.
- No hidden driver substitutions: driver resolution is canonical-slug
  based, recorded in the resolved context; unknown drivers fail with
  `CONTEXT_UNRESOLVED` rather than mapping to another driver.
- No hidden context changes: the run stores the **original** intake
  context (used for replay/continue) alongside the resolved context
  (used for execution), so what the user asked is always distinguishable
  from what the system resolved.
- WHY-questions are answered by the trace: `WHY_SELECTED` /
  `WHY_NOT_SELECTED` on hypotheses, `reason` on every decision.

## 6. API surface

- Autonomous routes are additive; no existing route changed semantics.
  `GET /api/investigations/autonomous/{run_id}` does not collide with the
  legacy `GET /api/investigations/{inv_id}` (the list route uses a
  distinct literal path).
- Error mapping is honest: unresolvable context → `CONTEXT_UNRESOLVED`
  (HTTP 422), missing data → `DATA_UNAVAILABLE` (HTTP 409), unknown run →
  404, invalid question → 400. No failure is reported as success.
- Run records persist under `data/autonomous_runs/` (gitignored runtime
  data), contain no credentials, and embed only deterministic output
  hashes — not raw large payloads.

## 7. Input handling

- Question text length is bounded; control characters are stripped during
  normalization before scanning.
- Structured context values (season, round, drivers, laps) are validated
  against canonical identifiers; out-of-range or non-existent values fail
  resolution instead of being clamped.
- No filesystem or SQL surface is reachable from question text; all data
  access goes through the existing parameterized canonical query layer.

## 8. Residual risks / limitations

- The injection scanner is pattern-based; novel phrasings of override
  attempts may not be *flagged* — but they also cannot take effect,
  because no code path treats question text as instructions. Flagging is
  observability, not the defense itself.
- The orchestrator reuses the engine's own eligibility and honesty rules;
  any future engine-side rule change flows through automatically, but
  golden hashes will then honestly report `CHANGED` on replay.
