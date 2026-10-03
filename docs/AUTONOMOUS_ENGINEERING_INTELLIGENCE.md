# RACEWISE — Autonomous Engineering Intelligence

How RACEWISE turns an engineering question into a falsifiable, traceable
investigation — and where it deliberately refuses to answer.

---

## 1. The authority rule

The deterministic engine is the numerical authority. Orchestration may interpret
questions, plan, select tools and organise evidence. It must **never**:

- invent telemetry, weather, tyre state, lap data or race results
- manufacture confidence or causal attribution
- override a deterministic calculation
- silently substitute unavailable data
- convert a modelled counterfactual into a historical fact
- alter a canonical output to make the UI look better

`SUPPORTED` means **"the evidence is consistent with this"**. It never means
"this caused it". Causation is not claimed anywhere in the engine.

---

## 2. Lifecycle

`src/racewise/data/historical/autonomous_investigator.py`

```
CREATED
  → QUESTION_PARSED
  → CONTEXT_RESOLVED
  → DATA_CHECKED
  → HYPOTHESES_SELECTED
  → EVIDENCE_PLANNED
  → EVIDENCE_COLLECTING
  → HYPOTHESES_EVALUATED
  → FALSIFICATION
  → COUNTERFACTUAL_CHECK
  → SYNTHESIS
  → VERIFICATION
  → COMPLETED
```

Terminal failure states are first-class and never hidden:

```
INVALID_QUESTION  CONTEXT_UNRESOLVED   DATA_UNAVAILABLE
INSUFFICIENT_EVIDENCE                   TOOL_FAILURE
MODEL_FAILURE         VERIFICATION_FAILURE
BUDGET_EXHAUSTED     UNSUPPORTED_QUESTION
```

Tool decisions are constrained to a closed allow-list:

```python
_TOOL_DECISIONS = {"SELECT_TOOL", "REQUEST_MORE_EVIDENCE", "RUN_COUNTERFACTUAL"}
```

---

## 3. Falsification semantics

`src/racewise/data/historical/evidence_fusion.py`

```
SUPPORTED · PARTIALLY_SUPPORTED · CONTRADICTED
NOT_SUPPORTED · NOT_TESTABLE · INSUFFICIENT_EVIDENCE
```

The critical distinction the engine preserves:

> **`NOT_SUPPORTED`** — *tested*, and the evidence fails to meet the rule.
> **`NOT_TESTABLE`** — the required evidence **does not exist**.

Collapsing these would turn missing data into a negative finding. That
distinction is the single most important epistemic property in the system.

Aggregation rules (`evidence_fusion.py:458-465`):

- `NOT_TESTABLE` — no evidence item from a required source exists
- `CONTRADICTED` — ≥1 valid evidence item CONTRADICTS
- `SUPPORTED` — ≥1 SUPPORTS and zero CONTRADICTS
- `PARTIALLY_SUPPORTED` — SUPPORTS present plus ≥1 non-decisive
- `NOT_SUPPORTED` — only non-decisive/insufficient (tested, inconclusive)

---

## 4. Contradictions are never collapsed

This is verified in live output, not just documented. A real investigation
(2023 R1, VER vs PER, lap 6) returns:

```json
"H1_corner_speed": {
  "aggregate_state": "MIXED_EVIDENCE",
  "supporting_evidence":   ["evidence_003", "evidence_004"],
  "contradicting_evidence": ["evidence_006"],
  "non_decisive_evidence":  ["evidence_002", "evidence_005"],
  "evidence_coverage": { "items_total": 5, "supporting": 2,
                         "contradicting": 1, "non_decisive": 2 },
  "falsification_status": "MIXED",
  "unresolved_contradictions": true
}
```

Note `contradicting_evidence` is a **separate list**, and
`unresolved_contradictions: true` is surfaced explicitly. A hypothesis
supported on early laps but contradicted later cannot silently become
"supported".

---

## 5. Residual-first

The observed delta minus explained components leaves a residual. The engine
**refuses to assign it to a mechanism** without evidence.

Live UI output for the same investigation:

```
OBSERVED DELTA          0.732 s   measured · evidence_001
UNASSIGNED RESIDUAL    -0.659 s   UNRESOLVED — never assigned to a mechanism
PRESERVED CONTRADICTIONS  6      never resolved away
```

The residual is displayed as a first-class finding, not distributed across
"driver error / tyre / aero / traffic" to make the explanation look complete.
That refusal is the product's differentiator.

---

## 6. Counterfactuals are MODELLED

A counterfactual is a bounded intervention under a stated model, reported with
its parameters, assumptions and limits — never as history.

UI labels every modelled quantity; a dedicated test enforces it:

```
✓ labels every modelled quantity MODELLED — NOT HISTORICAL (mandatory §11)
```

Race-level extrapolation is structurally ineligible and is reported as such
rather than approximated.

---

## 7. Provenance

Every result carries:

```
analytical_chain · method · investigation_version · layers_executed
provider · source_tables · assumptions · limitations · output_hash
```

`output_hash` is byte-stable across processes and hash seeds (§5 of
[PERFORMANCE_ARCHITECTURE.md](PERFORMANCE_ARCHITECTURE.md)) — the engine is
replayable and divergence is detectable.

### Provenance vocabulary (product rule)

The engine tags evidence with internal layer codes (`6E`, `6F`, …). These are
**build history, not engineering meaning**, and are never shown verbatim. They
are translated in `apps/web/src/workspace.tsx`:

| Code | User-facing label |
|---|---|
| 6E | Telemetry attribution |
| 6F | Evidence fusion |
| 6G | Stint evidence |
| 6H | Race gap decomposition |
| 6I | Telemetry counterfactual |
| 6J | Performance envelope |
| 6K | Performance regimes |
| 6L | Cross-race pattern |
| 6M | Cross-race evidence |
| 6N | Investigation synthesis |
| 6S | Engineering validation |

The underlying value is unchanged and still recorded — only the label differs.
A regression guard (`apps/web/src/provenance-vocabulary.test.ts`) scans every
view source and fails the build if a raw code reappears in rendered JSX.

---

## 8. Verified refusal behaviour

Adversarial cases run against the live API. **Returning `UNAVAILABLE` with zero
evidence is the correct outcome** — fabricating a result would be the bug.

| Case | Status | Evidence items |
|---|---|---|
| unknown driver (`zzz-nobody`) | `UNAVAILABLE` | 0 |
| unknown race (2099 R99) | `UNAVAILABLE` | 0 |
| missing lap (lap 999) | `UNAVAILABLE` | 0 |
| pre-telemetry era (1950) | `UNAVAILABLE` | 0 |

No fuzzy driver substitution. No silent race substitution. No widening of an
unavailable scope to something adjacent that would produce output.

---

## 9. What was audited and deliberately left unchanged

An explicit audit of Phases D/E of the brief found the requested intelligence
**already implemented and sound**:

| Requirement | Status before any change |
|---|---|
| 13-stage lifecycle | present in `autonomous_investigator.py` |
| Closed failure vocabulary | present |
| H1–H6 canonical hypotheses | present |
| Falsification result enum | present, incl. NOT_TESTABLE ≠ NOT_SUPPORTED |
| `evidence_conflicts` | present in the API contract |
| Residual as unassigned | present |
| Decision trace | present |
| Replay / output hash | present |

Rebuilding any of this would have violated the regression-safety requirement.
The engineering effort went into the measured startup defect instead.

---

## 10. Related documents

- [`PERFORMANCE_ARCHITECTURE.md`](PERFORMANCE_ARCHITECTURE.md)
- [`RACEWISE_DESIGN_SYSTEM.md`](RACEWISE_DESIGN_SYSTEM.md)
- [`GOLDEN_INVESTIGATIONS.md`](GOLDEN_INVESTIGATIONS.md)