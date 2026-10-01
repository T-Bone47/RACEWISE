# RACEWISE — Current-State UX Audit

**Scope:** `apps/web` frontend as shipped at commit `7783796` (Stitch-integrated).
**Method:** full-source inspection (all 24 view/component modules), the
Impeccable deterministic detector (9 findings), UI UX Pro Max design-intelligence
queries, and the product truth in `PRODUCT.md`.
**Format:** PROBLEM → IMPACT → PROPOSED CHANGE → RACEWISE CONSTRAINT.

---

## 1. Flagship exposes every layer at once (no progressive disclosure)

**PROBLEM:** `InvestigationView` renders a ~6-viewport vertical scroll:
observation band, hypothesis matrix, telemetry canvas, degradation, evidence
ledger, decision trace, graph, counterfactuals, synthesis, replay, compare,
memory — all simultaneously.
**IMPACT:** The user cannot tell what matters *now*; the telemetry canvas is
squeezed mid-scroll; the question (the product) loses dominance after the
first viewport.
**PROPOSED CHANGE:** Workstation layout: a lifecycle-true **stage rail**
(Observation / Hypotheses / Evidence / Falsification / Counterfactual /
Synthesis / Verification) gating the **dominant center canvas**, a persistent
**bottom decision-trace strip**, and the existing right inspector. Default
stage = Observation ("what matters now"); each later stage answers "why",
"how derived", "where from".
**RACEWISE CONSTRAINT:** Stages must map to real engine output only (6N
lifecycle + payload fields); stage status chips derive from the payload; the
engine is untouched.

## 2. Center canvas is not dominant

**PROBLEM:** The telemetry chart (`.tv-canvas`, ~260px tall) sits between
full-width tables; the graph panel below is full-width and competes.
**IMPACT:** The primary analytical instrument reads as one tile among many.
**PROPOSED CHANGE:** Observation stage gives the canvas ≥ 60% width and
primary height (≈ 380–420px), with the windows ledger as a secondary table;
graph/replay/memory move to the Verification stage.
**RACEWISE CONSTRAINT:** Only real aligned profiles (0.25 s grid) render; no
fabricated series when the scope is unavailable.

## 3. Duplicated render blocks in the flagship

**PROBLEM:** `InvestigationView` renders the context-controls form twice
(`result && …` and `!result && …` with identical JSX) and the `inv-meta` strip
twice; `TelemetryDeltaPanel` duplicates its fetch-key pattern.
**IMPACT:** Double DOM weight, drift risk between the copies, wasted renders.
**PROPOSED CHANGE:** Single controls block + single meta strip, extracted
into small components; remove the duplicates.
**RACEWISE CONSTRAINT:** Behavior (params, auto-run) unchanged.

## 4. AI-tell side-tab borders on non-status containers

**PROBLEM:** Detector: 8 occurrences of 2px colored `border-left` on banners,
error boxes, template pills, context chips, hypothesis dots — the "AI slop"
tell. (The committed Stitch badge structure legitimately uses it *only* for
epistemic status chips.)
**IMPACT:** Reads templated; erodes the "authored instrument" feel; on
non-semantic containers the accent means nothing.
**PROPOSED CHANGE:** Keep 2px left status border **only** on epistemic chips
(`.ef-badge`, `.claim-tag`); everything else gets a 1px `--st-line` border +
small status dot; remove accent from purely structural pills.
**RACEWISE CONSTRAINT:** Status must remain color-independent (text stays).

## 5. Layout-thrashing animation

**PROBLEM:** Detector: `transition: width` on chart loss bars.
**IMPACT:** Jank on dense re-renders.
**PROPOSED CHANGE:** Animate `transform: scaleX()` (transform-origin left),
static width.
**RACEWISE CONSTRAINT:** None (display-only).

## 6. Navigation IA does not match the workflow

**PROBLEM:** Sidebar groups are tool-shaped ("Command center / Data /
Engineering") and mix workflow stages with utilities; "Autonomous Query (6T)"
is engine jargon in the nav.
**IMPACT:** Users hunt for the investigation loop; knowledge vs analysis
surfaces are not separable at a glance.
**PROPOSED CHANGE:** Regroup existing routes 1:1 (no route removed):
**INVESTIGATION** (Command Center, Active Investigation, Falsification,
Counterfactual) · **KNOWLEDGE** (Investigation Graph, Engineering Memory,
Cross-Race Patterns, Pattern Evidence) · **ANALYSIS** (Lap Comparison, Lap
Attribution, Evidence Fusion, Stint Analysis, Race Gap, Performance Envelope,
Regime Timeline) · **DATA** (Sessions & Drivers) · **WORKSPACE** (Autonomous
Query, Compare, Replay).
**RACEWISE CONSTRAINT:** Every existing view id and route survives; only
grouping/labels change.

## 7. Command palette: keyboard cannot reach search results + missing context actions

**PROBLEM:** `ArrowDown` clamps the index to `filtered.length - 1` (commands
only) while `entries` includes typed search results; the mission-required
context actions (Copy Investigation ID, Export, Change Context, Run
Counterfactual, Trace Evidence) are absent; the command list is one flat 19-item
row.
**IMPACT:** A11y/interaction bug (keyboard users can never select search
results); the palette under-serves the workstation.
**PROPOSED CHANGE:** Fix the clamp; group commands (Investigation /
Navigate / Analysis / Data) with headers; add context-sensitive actions
(enabled per current route); ARIA listbox semantics.
**RACEWISE CONSTRAINT:** Only real actions; search stays exact/structured.

## 8. Kicker/eyebrow labels above headings

**PROBLEM:** `.t-microlabel` eyebrows sit above the flagship question and
several section headings (craft-floor ban: the heading must carry itself).
**IMPACT:** Adds a template feel and steals vertical space.
**PROPOSED CHANGE:** Delete decorative eyebrows; where the eyebrow carried
real information (e.g., "MODELLED · NOT HISTORICAL"), keep it as a status
*chip beside* the heading, not a label above it.
**RACEWISE CONSTRAINT:** Epistemic labels (MODELLED, state chips) remain
mandatory — repositioned, not removed.

## 9. Hypothesis experience is a flat table

**PROBLEM:** The flagship renders hypotheses as a plain 7-column table;
states and counts are readable but the rows don't communicate the loop
(prediction → evidence → verdict).
**IMPACT:** Users read numbers, not the falsification story.
**PROPOSED CHANGE:** Hypothesis stage renders compact hypothesis rows: id +
name, statement, supporting/contradicting counts as inline chips, state chip;
row click focuses the hypothesis (evidence filter + graph focus + inspector).
**RACEWISE CONSTRAINT:** Exact backend states; no ranking, no per-hypothesis
deltas, no percentages.

## 10. Decision trace is a side list, not a timeline

**PROBLEM:** The trace renders as a long `<ul>` beside the evidence ledger.
**IMPACT:** The "where am I in the reasoning" story is buried mid-scroll.
**PROPOSED CHANGE:** Persistent bottom **trace strip**: one compact node per
trace entry (id + status dot), horizontally scrollable, expandable to the full
detail; focused/selected trace highlights its basis evidence.
**RACEWISE CONSTRAINT:** Trace entries/basis come from the payload verbatim.

## 11. Chart language divergence

**PROBLEM:** The flagship canvas (`.tv-*`), the older analytical views
(`.rg-*` bars, regime/pattern charts), and the falsification sparkline each
style axes/grids/legends differently.
**IMPACT:** The product reads as several apps stitched together (mission §26).
**PROPOSED CHANGE:** One shared chart frame (`.rws-chart`: recessed viewport,
dashed grid, mono 10px ticks + units, legend chip row, crosshair conventions)
applied to the flagship canvas, the falsification trace, and via CSS to the
existing view charts.
**RACEWISE CONSTRAINT:** No chart computes engineering values client-side.

## 12. Ad-hoc empty / insufficient / error states

**PROBLEM:** `.empty-state` carries long prose, lacks structure (AVAILABLE /
MISSING) and follow-up actions; errors are visual-only (no `role="alert"`).
**IMPACT:** Honest states exist but read as afterthoughts; screen readers miss
async failures.
**PROPOSED CHANGE:** A `StatePanel` primitive (kind: empty | insufficient |
unavailable | error | loading; title; reason; available[]; missing[];
action), with `role="alert"`/`aria-live` on error, used across the flagship
and matrix views.
**RACEWISE CONSTRAINT:** These states are first-class product results — the
copy must name the condition and the recovery, never fill the gap.

## 13. Accessibility gaps

**PROBLEM:** No `color-scheme: dark` (native inputs/scrollbars mismatch);
focus rings inconsistent across custom controls; the new persistent bottom
strip must not obscure focused elements; adjacent chip targets sit < 8px
apart in places.
**IMPACT:** Keyboard/AT users get second-class feedback.
**PROPOSED CHANGE:** `color-scheme: dark`; one `:focus-visible` standard;
`scroll-padding` for the trace strip; 8px target gaps; tab order = visual
order (rail → canvas → trace).
**RACEWISE CONSTRAINT:** None — pure quality floor.

## 14. Responsive behavior is partial

**PROBLEM:** Breakpoints exist for matrix/lab columns and the inspector
drawer, but the flagship scroll never restructures; rail/tablet/phone modes
were not designed as such.
**IMPACT:** Tablet (1024–1280) shows a cramped mid-scroll; phone is unusable.
**PROPOSED CHANGE:** ≥1280: full workstation. 1024–1280: rail collapses to a
horizontal stage chip bar; inspector becomes a drawer. <1024: single column
stacked in loop order (Question → Observation → Hypotheses → Evidence →
Conclusion). 375: readable stacked mode with 16px value floor.
**RACEWISE CONSTRAINT:** Mobile shows the same real data, re-flowed — never a
reduced "lite" dataset.

## 15. Template pills read as a mini card-wall

**PROBLEM:** Command-center templates render as 8 two-line bordered tiles with
accent side-bars.
**IMPACT:** Template feel (detector-flagged); the launcher CTA competes with 8
equal boxes.
**PROPOSED CHANGE:** Compact single-line pill row (label + short hint on
hover via title), 1px border, no accent bar; the launcher remains the single
dominant CTA.
**RACEWISE CONSTRAINT:** All 8 templates remain real question types.

## 16. Status bar claims without evidence

**PROBLEM:** The status bar always prints "DETERMINISTIC CHAIN READY" even if
the API is unreachable.
**IMPACT:** A status surface that can lie contradicts the product's core
promise.
**PROPOSED CHANGE:** Drive the status text from the last catalog fetch result
(available / unreachable), keeping the deterministic-chain language only when
true.
**RACEWISE CONSTRAINT:** No polling loops; reuse existing fetches.

## 17. Long-form section intros everywhere

**PROBLEM:** Many panels open with 2–3-line explanatory paragraphs
(muted `.small` prose) before content.
**IMPACT:** Vertical noise; the product explains itself instead of working.
**PROPOSED CHANGE:** Move explanations into `title` tooltips / an
"about this stage" affordance; keep one-line context where semantics require
(e.g., MODELLED disclaimers).
**RACEWISE CONSTRAINT:** Legally/epistemically required labels (MODELLED —
NOT HISTORICAL, residual disclaimers) stay visible.

---

## Detector + guidance summary (inputs to the fixes above)

- **Impeccable detect (9):** 8× thick colored side borders on non-chip
  containers; 1× `transition: width`.
- **UI UX Pro Max (RACEWISE-filtered):** 8px min target gaps; 4.5:1 contrast
  floor (aim 7:1 for data values); `color-scheme: dark`; `role="alert"` for
  errors; empty states with reason + action; JetBrains Mono weight-400
  discipline, line-height 1.2 for density; tab order = visual order;
  persistent UI must not obscure focus (scroll-padding); reduced-motion
  final states; transitions sized by distance (~200ms color feedback).
