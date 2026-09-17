# RACEWISE — Decision Log (ADR-style)

## ADR-001 — Data source: FastF1 primary, OpenF1 secondary
**Decision:** Use FastF1 as the primary adapter for the MVP.
**Why:** Verified working in this environment (1056-lap pull, 2023 Bahrain); lap-level timing, stints, compounds, tyre life, track status and pit windows all present in one normalized dataframe. OpenF1 adds little for historical analysis and adds an extra integration surface.
**Consequence:** OpenF1 adapter deferred; adapter interface keeps it replaceable.

## ADR-002 — Investigation loop is bounded and adaptive, not scripted
**Decision:** The agent selects tools adaptively each round from an allow-list, but the engine enforces a hard budget and a mandatory falsification phase before synthesis.
**Why:** Satisfies both "the agent genuinely investigates" and "no fake agent pretending to reason" without risking unbounded loops or runaway cost.
**Consequence:** A `max_rounds` budget and an explicit falsification gate are part of the investigation contract.

## ADR-003 — Numbers never come from the model
**Decision:** Any numeric claim in a final report must reference a tool-executed observation; verification rejects unsupported numeric claims.
**Why:** Core product principle (Principle A in the research brief).
**Consequence:** Report synthesis receives only tool outputs; the verification phase checks claim→evidence linkage.

## ADR-004 — Degraded mode is honest, not simulated
**Decision:** If no model provider is configured, investigations run in deterministic-only mode; UI/report explicitly state model-dependent phases are unavailable.
**Why:** Environment has no OpenRouter credentials; faking an LLM would violate the no-fake-features rule.
**Consequence:** The investigation engine has two entry paths: `agent` (requires provider) and `deterministic` (hypotheses/tool plan from a rules-based investigator that is clearly labeled as non-AI).

## ADR-005 — Confidence is computed, not vibes
**Decision:** Hypothesis confidence is derived from evidence strength (supporting vs contradicting observation counts and effect sizes), documented in the tool/method version.
**Why:** The spec demands a defined method behind any displayed confidence number.
**Consequence:** Confidence formula lives in one audited function with unit tests.

## ADR-006 — Verified session slice for tests
**Decision:** 2023 Bahrain Race is the reference fixture; known values (VER stints, pit laps 14/36, 57-lap race) are asserted in tests.
**Why:** Tests need a fixed, verified truth; this session was pulled and inspected during the audit.
**Consequence:** Benchmarks and unit tests share this fixture; other sessions added later must get the same treatment.
