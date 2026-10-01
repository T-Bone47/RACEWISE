# PRODUCT.md — RACEWISE durable product truth

**Product:** RACEWISE — autonomous, evidence-driven race engineering.
**One-liner:** An engineering investigation workstation that answers real Formula 1
engineering questions with deterministic analysis, explicit falsification, and
fully traceable evidence — never fabricated data.

## Audience

- **Primary:** race engineers, performance/strategy analysts, and engineering
  managers who need defensible answers about *why* a lap, stint, or race gap
  happened — and what would have happened under a stated intervention.
- **Secondary:** researchers and technical staff evaluating the evidence chain
  itself (provenance, replay, memory).
- **Not the audience:** fans, media, consumers. No entertainment framing.

## Purpose

Replace ad-hoc telemetry spelunking with a disciplined investigation loop:

QUESTION → CONTEXT → OBSERVATION → HYPOTHESES → EVIDENCE → FALSIFICATION →
COUNTERFACTUAL → SYNTHESIS → PROVENANCE → REPLAY

The user must always know where they are inside this loop, and every displayed
number must be traceable to a real API response, a real canonical data row, or
a clearly labelled MODELLED result.

## Operating context

- Dark, desk-based, long sessions on 1920×1080 / 1440×900 workstations; tablet
  and field-laptop sizes must degrade gracefully; phone is a reading fallback.
- High information density is expected and desired — density is structured by
  hierarchy, never by tiny text.
- Decisions are made under epistemic discipline: the product displays
  `UNAVAILABLE`, `INSUFFICIENT_EVIDENCE`, `NOT_TESTABLE` as first-class
  results and never papers over them.

## Durable facts (product truth — the UI may never contradict these)

1. **The deterministic engine owns all computation.** The frontend renders; it
   never computes engineering results. Same input → same output → same replay
   → same hashes.
2. **Canonical hypothesis set:** H1 Corner Speed · H2 Throttle · H3 Braking ·
   H4 Tyre State · H5 Race Control · H6 DRS — with the closed state vocabulary
   SUPPORTED · PARTIALLY_SUPPORTED · NOT_SUPPORTED · CONTRADICTED ·
   NOT_TESTABLE · INSUFFICIENT_EVIDENCE · MIXED_EVIDENCE · NOT_REQUESTED.
   No invented states, no confidence percentages, no ranking, no "best"
   hypothesis.
3. **The residual stays unassigned.** An unresolved residual is displayed as
   UNRESOLVED and is never attributed to a mechanism without evidence.
4. **Counterfactuals are MODELLED — NOT HISTORICAL.** Every counterfactual
   surface carries that label; historical and modelled data are visually
   separated.
5. **Telemetry truth:** six real channels (speed, throttle, brake, gear, rpm,
   drs), native ~3.7 Hz provider samples resampled onto a 0.25 s analysis
   grid. There is no 100 Hz data, no distance/corner axis, no FIA feed, no
   tyre temperatures, no ERS state — and the UI never implies otherwise.
6. **The graph is the Phase 6P engineering investigation graph** — typed,
   provenance-backed, derived on read. It is never presented as a causal DAG.
7. **Memory is scope-exact and derived on read.** No invented counts, no
   semantic "similar investigation" claims.
8. **Replay is real:** re-run and hash comparison, with `IDENTICAL` /
   `DIFFERENT_*` states. Never a simulated success.

## Voice and copy rules

- Precise, calm, engineering register. Controls name their action
  ("Run counterfactual", "Export investigation").
- States name the condition and the recovery ("No telemetry ingested for this
  session under the bounded policy — choose a covered session").
- Never marketing language, never exclamation, never fabricated urgency.

## Constraints

- React 19 + Vite + TypeScript frontend at `apps/web`; FastAPI engine at
  `src/racewise`. The engine is sacred: 6E–6T outputs must remain unchanged.
- The Stitch design language (dark graphite ladder, restrained cyan accent,
  epistemic state colors, Inter narrative + JetBrains Mono engineering
  numerals) is the committed visual world.
- Every interactive control must call a real capability or render an honest
  unavailable state. No dead controls, no decorative data.
