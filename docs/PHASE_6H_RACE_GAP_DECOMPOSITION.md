# Phase 6H — Race-Level Gap Decomposition Methodology

How RACEWISE determines *"where during the race was the performance
relationship between Driver A and Driver B created, recovered, or changed —
and which portions of that evolution are evidence-supported, context-driven,
or unresolved?"*

Companion to `PHASE_6H_COMPLETION_REPORT.md` (measured results),
`PHASE_6G_STINT_EVIDENCE.md` (stint layer), `PHASE_6F_EVIDENCE_FUSION.md`
(lap layer).

## 1. Design position

Phase 6H is an **orchestration/aggregation layer** over 6E lap attribution,
6F lap fusion and 6G stint fusion — nothing underneath is rewritten. The
output is an **evidence map, not a race narrative**: every statement is
generated from deterministic structured facts, and the observable categories
are never collapsed into one story.

## 2. What RACEWISE does NOT claim

- It does NOT claim "time lost": the output uses *observed gap* /
  *comparable gap* language only.
- It does NOT reconstruct the official finishing gap from lap sums; the
  official gap comes from canonical result milliseconds (equal laps, equal
  classification status required) and is an authoritative fact.
- It does NOT force `official_gap = analytical_gap + residual`; the two gap
  quantities are different and are reported side by side with the
  relationship stated ("no equality is implied").
- It does NOT attribute pit-window gap changes to stop duration, undercut,
  traffic or tyres; the mechanism is `INSUFFICIENT_EVIDENCE` by design — only
  the observed transition is reported.
- It does NOT extrapolate telemetry evidence across uncovered segments.
- It does NOT classify a whole race as wet/restricted from a session-level
  event; race control and weather use exact lap-window overlap.

## 3. Pipeline

```
canonical race + result identity (participants validated)
  → official classified gap (canonical results, authoritative)
  → chronological lap timeline (comparable / non_comparable / unavailable + reasons)
  → stint segmentation (driver A canonical stint identity)
  → descriptive per-segment gap patterns (bounded OLS, thresholds documented)
  → gap events (3-lap window slope changes, stint changes, evidence changes)
  → bounded 6G stint-evidence chaining (ranked by telemetry coverage, max_segments)
  → race-level hypothesis evolution (stint summaries → race rule)
  → pit windows, race-control windows (exact lap overlap)
  → residual accounting + official-vs-analytical relationship
  → evidence-bounded synthesis
```

## 4. Comparable-lap definition

A lap is comparable when BOTH drivers have a canonical lap fact with a valid
time, neither carries `is_pit_in_lap` / `is_pit_out_lap` / `deleted`, and no
race-control restriction overlaps the lap (exact lap field). Laps where one
driver has no lap fact are `unavailable` (retirement, off-sequence). Nothing
is dropped: every excluded lap carries its reason in the timeline and the
timeline summary tallies reasons.

## 5. Gap events

Deterministic event types: `GAP_WIDENING` / `GAP_NARROWING` (3-lap window OLS
slope sign/magnitude change, threshold 0.02 s/lap, documented),
`STINT_CHANGE`, `TELEMETRY_EVIDENCE_CHANGE`. No subjective labels.

## 6. Race-level hypothesis evolution

Each of the six 6F hypotheses is summarized per stint by 6G, then aggregated
by a race rule: contradictions without support → `CONTRADICTED_OVER_TIME`;
all-evaluable support → `CONSISTENTLY_SUPPORTED`; mixed →
`INTERMITTENTLY_SUPPORTED`; nothing evaluable → `INSUFFICIENT_EVIDENCE`.
Contradictions on one stint and support on another are **both preserved** —
never averaged away. Per-stint detail travels in the output.

## 7. Residual accounting

Hierarchy preserved: lap (`observed = pace component + residual`) → stint
totals → race analytical accounting over comparable laps. The report shows
comparable / non-comparable / unavailable counts explicitly, plus the
statement that the official and analytical gaps are different quantities.
The residual is reported, never assigned to tyres, telemetry, braking,
throttle or race control without independent evidence.

## 8. Source independence and no invented continuity

Per-lap 6F `source_id` uniqueness and 6G per-lap observation identity are
preserved; race-level summaries aggregate statuses, never re-derive evidence,
so lap/sector/stint deltas derived from the same lap facts are not counted as
independent confirmations. Missing telemetry, insufficient stint laps,
unknown weather and untestable race-control timing are preserved as
UNAVAILABLE / INSUFFICIENT_EVIDENCE / NOT_TESTABLE — never interpolated.

## 9. Storage, determinism, bounds

Derived on read (zero storage growth, size+mtime proven unchanged).
Byte-identical output for the same store + `race_gap_v1` (in-process, fresh
subprocess, MCP). MCP bounds: `max_segments` 2–24 enforced explicitly in the
tool (the generic payload validator ignores numeric ranges), unknown
parameters rejected, no raw telemetry dumps (bounded 6G chaining only).
