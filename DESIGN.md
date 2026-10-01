# DESIGN.md — RACEWISE design system

**Visual authority for the RACEWISE engineering investigation workstation.**
Source of truth: the token layer in `apps/web/src/App.css` (pinned by
`apps/web/src/design-system.test.ts`). This file regenerates the earlier,
superseded design doc (pre-Stitch: F1-red accent, Geist fonts) to match the
shipped system: the Stitch design language, refined into a workstation.

**Design read:** pit-wall instrumentation meets scientific analysis software.
Not a SaaS dashboard, not a marketing site. The interface is an instrument:
precision, evidence, investigation, traceability, control.

## Dials

| dial | value | meaning here |
|---|---|---|
| DESIGN_VARIANCE | 7 | authored composition — dominant center canvas, left stage rail, persistent bottom trace — but analytical clarity always wins |
| MOTION_INTENSITY | 3 | motion communicates state change only, 120–200 ms, ease-out, no bounce; `prefers-reduced-motion` renders final states |
| VISUAL_DENSITY | 8 | dense ledgers and tables structured by hierarchy — never by tiny text (12px floor for engineering values) |

## Tokens (implemented — see `:root` in App.css)

### Surface ladder (dark graphite, one family)
```
--st-canvas    #0b0e12   Layer 0 — app background
--st-recessed  #0e1014   Layer 1 — chart viewports, trace tracks
--st-surface   #111418   Layer 2 — docked panels
--st-element   #171b22   Layer 3 — inputs, active cells, nested tables
--st-hover     #1e232c   interactive hover
--st-line      #232934   hairline borders, grid
--st-line-hi   #2f3746   focused edges
```
Elevation is tonal stepping + 1px hairlines. No shadows except the Layer-4
overlay (`--st-shadow-overlay`, hard-edged, achromatic). Zero panel radius;
4px interactive radius (`--st-radius-el`); no pill shapes.

### Signal accents (restrained)
```
--st-primary        #00e5ff   cyan — cursors, active stage, focus (fills ≥3:1 as text AA uses --st-primary-text #9cf0ff)
--st-secondary      #3875ff   indigo — structural actions, reference driver
--st-secondary-text #b3c5ff   AA-safe indigo text
--st-error          #ffb4ab   AA-safe error text
--st-error-strong   #ef4444   epistemic CONTRADICTED
```
The accent is earned: one cyan per view for *where you are and what is live*,
not decoration.

### Epistemic state engine (semantic color is truth, never decor)
```
--ep-fact        #3b82f6   FACT            --ep-supported    #10b981
--ep-calc        #06b6d4   CALCULATION     --ep-partial      #f59e0b
--ep-infer       #f59e0b   INFERENCE       --ep-contradicted #ef4444
--ep-cf          #8b5cf6   COUNTERFACTUAL  --ep-assume       #64748b
```
Status is never color-only: every state chip carries its text and a 2px left
status border (the one place a thick left accent is used — the committed badge
structure). Non-status containers use 1px borders and a status dot.

### Typography
- **Inter Variable** — narrative UI, questions, findings, controls. Tracking
  −0.01…−0.02em on display sizes; body 13px/1.5.
- **JetBrains Mono Variable** — every engineering value, id, hash, time,
  axis, kbd. Weight discipline: 400/500/700 for emphasis only;
  `font-variant-numeric: tabular-nums` everywhere values align.
- Scale: 28px question · 20px view title · 14px section head · 13px body ·
  12px table · 11px chip · 10px axis. Nothing below 10px. The investigation
  question is the largest type on its screen — it is the product.
- `color-scheme: dark` so native surfaces (scrollbars, inputs, caret) match.

### Chart language (one instrument voice)
All analytical charts share: recessed viewport (`--st-recessed`), dashed
1px `--st-line` grid, mono 10px ticks with explicit units, target driver =
cyan / reference driver = indigo dashed / counterfactual = violet dashed,
crosshair with live mono readout, honest origin ("0.25 s analysis grid"),
legend chips above, no glow, no gradients. The chart answers a question — its
title is a question ("Speed — VER vs PER, lap 57"), never "Dashboard".

### Motion
`--speed: 150ms` color/opacity feedback; `--speed-panel: 240ms` surfaces;
`--speed-view: 320ms` stage changes. Ease-out, no bounce, no layout-thrashing
properties (transform/opacity only; never width/height). One authored moment
per view (e.g., the stage transition on the flagship).

## Layout system

### App shell
36–56px top bar (brand · scope crumb · ⌘K search · context chips) · left
navigation deck grouped by workflow (INVESTIGATION / KNOWLEDGE / ANALYSIS /
DATA / WORKSPACE) · workspace · status bar (real system state only).

### Flagship workstation (Active Investigation)
```
┌─ investigation header: question (dominant) + measured context + observation band
├─ stage rail   │  CENTER — dominant analytical canvas for the selected  │ inspector
│ (7 stages,   │  stage (observation / hypotheses / evidence /             │ (context
│  lifecycle-   │  falsification / counterfactual / synthesis /           │ drawer on
│  true, real   │  verification)                                          │ selection)
│  statuses)    ├─ decision trace strip (persistent bottom timeline)      │
└─────────────────────────────────────────────────────────────────────────┴─
```
- **Left rail** = where you are in the loop, with real per-stage status.
- **Center** is ≥ 60% of the width and owns the chart.
- **Right inspector** opens on selection; collapses to a drawer under 1180px.
- The four information layers never show at once: NOW (observation band) →
  WHY (hypotheses) → HOW (evidence/trace) → WHERE FROM (provenance drawer).

### States
Every async surface implements the full state set — loading (skeleton),
empty (reason + one action), insufficient evidence (AVAILABLE / MISSING
lists), unavailable, error (`role="alert"`, names problem + recovery). Gaps
are never filled with fabricated visuals.

## Accessibility floor

- Contrast ≥ 4.5:1 body/data on graphite (muted `#bac9cc` ≈ 9:1; critical
  values never in outline gray).
- Visible `:focus-visible` ring (1px cyan, offset) on every interactive
  element; tab order = visual order; no keyboard traps; drawers manage focus.
- Full keyboard: ⌘/Ctrl K palette, Esc close, arrows navigate, Enter run.
- `prefers-reduced-motion` renders final states without animation.
- 8px minimum gap between adjacent click targets.

## What this design refuses

Card walls · nested cards · purple/pink gradients · glass decoration · glow ·
emoji icons · fake HUD · confidence percentages · 100 Hz claims · causal-graph
claims · invented channels or counts · kicker/eyebrow labels above headings ·
numbered sections where the number carries no information · dead controls.
