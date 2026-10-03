# RACEWISE Design System — Component & Convention Reference

**Visual authority:** root `DESIGN.md` (tokens, palette, typography, chart language).
**Token implementation:** `apps/web/src/App.css` `:root` — pinned by
`apps/web/src/design-system.test.ts` (which also enforces the fabrication guard).
**Product truth:** root `PRODUCT.md`.

This document maps the RWS component inventory (mission §6), the conventions
every surface must follow, and where each one is implemented. It is the
frontend contract: new UI must reuse these primitives instead of inventing
parallels.

---

## 1. Information architecture (routes)

| Route | View | Stage in the loop |
|---|---|---|
| `#/command` | Command Center | START — launcher, templates, 6T console, recents ledger |
| `#/investigate` | **Active Investigation (flagship)** | the whole loop, stage-gated |
| `#/falsification` | Falsification Matrix | FALSIFICATION (prediction → criterion → evidence → verdict) |
| `#/counterfactual` | Counterfactual Lab | COUNTERFACTUAL (MODELLED — NOT HISTORICAL) |
| `#/graph` `#/memory` `#/patterns` `#/patternevidence` | Knowledge views | PROVENANCE / RECALL |
| `#/telemetry` `#/attribution` `#/fusion` `#/stint` `#/racegap` `#/envelope` `#/regime` | Analysis views | single-facet deep dives |
| `#/catalog` | Sessions & Drivers | DATA |
| `#/autonomous` `#/compare` `#/replay` | Workspace utilities | 6T console · dimension deltas · deterministic replay |

Sidebar groups: **Investigation · Knowledge · Analysis · Data · Workspace** —
workflow-shaped, not tool-shaped. Every route above is reachable from the deck
(pinned by `app-shell.test.tsx`).

## 2. Flagship workstation layout (Active Investigation)

```
┌ inv-hero: question (largest type on screen) · inv-actions · ContextStrip ·
│ observation band (metric strip) · inv-meta (id, hash, chain, provenance)
├ inv-controls (one instance, real params)
├ inv-workstation ┌ stage-rail (left, sticky)  ┐ ┌ stage-center (dominant) ┐
│                 │ Observation · Hypotheses ·  │ │ one stage at a time,    │
│                 │ Evidence · Falsification ·  │ │ ≥60% width, chart-first │
│                 │ Counterfactual · Synthesis ·│ │                         │
│                 │ Verification (+ matrix link)│ │ trace-strip (bottom,    │
│                 └─────────────────────────────┘ │ always present)         │
└ ContextInspector (right, opens on selection; fixed drawer ≤1280px)
```

- **Progressive disclosure:** NOW (observation band) → WHY (Hypotheses) →
  HOW (Evidence/Falsification) → WHERE FROM (provenance inspector,
  Verification). The rail is the lifecycle; stage statuses are real payload
  facts (e.g. `4 items · 0 conflicts`, `mixed evidence`).
- **Keyboard:** rail buttons are tabbable; ↑/↓ moves between stages; every
  trace node, window row and evidence chip is a real control.

## 3. RWS component inventory → implementation

| RWS component | Implementation | Notes |
|---|---|---|
| AppShell | `App.tsx` + `.shell` | header / sidebar / workspace / statusbar grid |
| TopBar | `.shell-header` | brand · scope crumb · ⌘K trigger |
| Sidebar | `.shell-sidebar` + `NAV` | 5 workflow groups, tabler icons |
| ContextBar | `ContextStrip` (`stitch.tsx`) | real compound/tyre-life/position/weather/coverage chips |
| InvestigationHeader | `.inv-hero` + `.inv-question` | the question is the product |
| Metric | `.metric-strip` cells | only payload-derived values |
| StatusBadge | `StateChip` + `.ef-badge` | canonical 8-state vocabulary, text never omitted |
| HypothesisRow | `.hyp-row` (flagship) — click opens the **HypothesisDetails drawer** (prediction / evidence / criterion / result / limitations) | expandable inline detail removed (round 2) |
| EvidenceRow | ledger `<tr>` + `ClaimTag` + **EFFECT column** (`→ H1` supports / `↮ H1` contradicts — real relations) | drawer for provenance detail |
| EvidenceDrawer | `ContextInspector` / `Drawer` + `EvidenceDetails` | back-stack navigation |
| FocusMode | `.shell.zen` + `.zen-exit` (Ctrl/Cmd+Shift+F) | hides nav/status, maximizes analysis |
| TelemetryChart | `SpeedProfileCanvas` (`stitch.tsx`) | zoom, drag-region, crosshair HUD, window bands |
| ChartToolbar | `.tv-toolbar` + `.tv-zoom` | badges + zoom controls |
| FalsificationPanel | `FalsificationMatrixView` + flagship Falsification stage | §15 structure |
| CounterfactualLab | `CounterfactualView` | ribbons, gates, profile canvas, 6J sweep |
| SensitivityChart | cf-lab sweep table + envelope view | real scenario points only |
| RegimeTimeline / PatternComparison | `PerformanceRegimeView` / `PerformancePatternView` | engine payloads |
| GraphCanvas | `GraphPanel` (`panels.tsx`) | 6P typed nodes/edges, focus + trace |
| GraphInspector | graph node detail + `/evidence` `/hypothesis` traces | provenance-backed |
| DecisionTrace | `.trace-strip` (persistent) + detail expansion | basis links to evidence ids |
| ProvenancePanel | `ProvenanceDetails` + provenance drawer | source/method/hash/limitations |
| MemoryPanel | `MemoryPanel` (`panels.tsx`) | scope-exact + related, no invented counts |
| ReplayPanel | `ReplayPanel` (`panels.tsx`) | IDENTICAL / DIFFERENT_* only |
| CommandPalette | `CommandPalette.tsx` | grouped commands + context actions + structured search |
| Search | palette search section | exact/structured only |
| EmptyState / InsufficientEvidence / ErrorState | `StatePanel` (`workspace.tsx`) | AVAILABLE/MISSING lists + `role="alert"` on errors |

## 4. UX conventions

- **Question-first:** every investigation surface leads with the question and
  the observation; tools never introduce themselves before the data.
- **One accent:** cyan = "where you are / what is live". Semantic colors only
  for epistemic states. No decorative color.
- **Numbers are mono + tabular:** every engineering value, id, hash, time uses
  JetBrains Mono with `tabular-nums`; narrative text is Inter.
- **States before content:** every async surface implements loading/empty/
  insufficient/unavailable/error via `StatePanel` or `StructuredError`; honest
  states are results, not failures.
- **MODELLED is loud:** counterfactual surfaces carry the badge
  `MODELLED — NOT HISTORICAL` and never mix into historical values.
- **Residual stays unresolved:** displayed as `UNRESOLVED — never assigned to a
  mechanism`, never attributed.
- **Motion:** 150ms color/opacity, 200ms surfaces, 320ms layout; ease-out
  only; `prefers-reduced-motion` renders final states; no layout-thrashing
  properties (bars animate via transform, never width). See §4a for the full
  motion system.

### 4a. Motion system (implementation — `src/motion.ts`)

Motion communicates state, never decorates. The JS token layer and the CSS
token layer share one scale (pinned by `src/motion-system.test.ts`):

| Token | Value | Used for |
|---|---|---|
| `DUR.micro` / `--motion-fast` | 150ms | color/opacity feedback, content fades |
| `DUR.panel` / `--motion-normal` | 200ms | inspectors, drawers, palette, stage switch |
| `DUR.layout` / `--motion-slow` | 320ms | shared-element flight, collapse |
| `EASE_OUT` / `--motion-ease` | `cubic-bezier(0.2,0,0,1)` | the one easing family |
| `SPRING` / `SPRING_DRAWER` | stiffness 420/320 · damping 42/38 | critically damped — zero overshoot |

Entrance variants (`V.*`): `riseIn`, `viewIn`, `inspectorIn`, `drawerIn`,
`paletteIn`, `backdrop`.

**Wired motion — each answers "what changed / where from / what is selected":**

- **Nav instrument cursor:** one `layoutId` glides between sidebar destinations.
- **Investigation load:** two coordinated phases — the observation band settles
  (keyed by investigation id), then the workstation rises. No 30-element stagger.
- **Stage switch:** keyed 200ms rise on the center — "focus changed", not "page changed".
- **Hypothesis → inspector:** the row's H-badge is a shared `layoutId` — the
  SAME badge flies into the inspector head and returns on close: "the same
  object becoming more detailed".
- **Inspector/drawer:** spring entrance (x+opacity, no bounce), stable head,
  interruptible 150ms content fade keyed by object identity (Evidence A→B
  never rebuilds the panel).
- **Workspace view change:** 200ms keyed rise; Suspense fallbacks stay instant.
- **Focus mode:** sidebar/statusbar fade out, workspace expands; the CSS grid
  final state collapses instantly (Motion owns opacity — no width jank).
- **MODELLED layer:** the counterfactual trace re-fades on scenario change
  (keyed by the real intervention fraction); observed traces never move.
- **Palette:** animated open (~150ms), instant close — keyboard speed first.
- **Skeleton:** a quiet 1.6s opacity breathe, disabled under reduced motion.

**Never animated:** engineering values (no numeric interpolation of any
backend number) · the telemetry crosshair (immediate) · observed/measured
traces (only the MODELLED layer crossfades) · the graph (static; motion only
for focus/selection colors) · no parallax, no infinite loops, no `whileHover`
springs, no free drag (drag exists only as the canvas region-selection gesture).

**Reduced motion (mandatory):** `<MotionConfig reducedMotion="user">` wraps
the shell — layout/transform animations collapse to instant, opacity fades are
preserved, and the CSS layer zeroes every transition under
`prefers-reduced-motion: reduce`. No interaction depends on seeing motion.

**Motion must never gate first paint (measured):** the workspace used to mount
at `opacity: 0` and fade in over 200 ms (`V.viewIn`). Chrome cannot report
first contentful paint while content is fully transparent, so the entrance
animation was delaying first paint. Only the *first* commit now skips it:

```tsx
initial={hasCommitted ? V.viewIn.initial : false}
```

`hasCommitted` is set from an effect, which React runs after paint, so the extra
render cannot affect first paint. Every later navigation still animates — that
is what motion is *for*. Motion is information architecture; it is never the
reason the product feels slow. See
[PERFORMANCE_ARCHITECTURE.md §6](PERFORMANCE_ARCHITECTURE.md).

**One icon family:** tabler only. A second family was removed rather than
tolerated — competing icon languages are a visual defect, not a preference.

### 4b. Prose: no internal implementation language

The user sees engineering concepts, never build history. Internal layer codes
(`6E`, `6F`, `6N`, …) must never appear in a heading, caption or label; they
are translated by `analyticalLayerLabel()` / `formatAnalyticalChain()` in
`src/workspace.tsx`. The raw codes remain in the payload and provenance
inspector, where they are legitimate.

This is machine-enforced: `provenance-vocabulary.test.ts` scans every view
source and fails if a bare code reappears in rendered JSX.
- **Copy:** controls name their action; errors name the condition and the
  recovery; no marketing register, no exclamation marks.

## 5. Accessibility floor

- `color-scheme: dark`; native scrollbars/carets themed.
- `:focus-visible` ring on every interactive element (1px cyan, offset).
- Tab order = visual order (rail → canvas → trace); drawers manage focus,
  Esc closes overlays globally (no keyboard traps).
- ⌘/Ctrl+K palette; ↑↓ navigate all entries; Enter runs; Esc closes.
- Status is never color-only — every state chip carries text.
- 8px minimum gap between adjacent targets; 44px rail target height;
  24px zoom-control height.
- Contrast: body/data ≥4.5:1 on graphite; muted `#bac9cc` ≈ 9:1.

## 6. Responsive contract

| Width | Behavior |
|---|---|
| ≥1280 | full workstation; inspector as right column (sticky) |
| 1024–1280 | rail → horizontal stage chips; inspector → fixed drawer |
| 768–1024 | single column, stages still chip-shaped, report grid stacks |
| ≤768 | mobile stack in loop order; metric strip 2-col; question 19px |

No "lite" dataset at any width — the same real data re-flows.

## 7. Performance conventions

- No client-side engineering computation; charts render payload values.
- Fetches keyed by scope composite; cancelled on unmount; no polling.
- One instance of any panel per view (deduplicated controls/meta).
- Lists bounded by the engine (caps are server-side).
- Production build ≤ ~100KB gzip for the shell (code-split views).
  **Current: 123.3 kB gzip entry** — the target is aspirational and is NOT met;
  the floor is ~220 kB minified react-dom alone. Measured breakdown and the
  rejected Motion tree-shaking option are documented in
  [PERFORMANCE_ARCHITECTURE.md §4](PERFORMANCE_ARCHITECTURE.md) so the gap is
  not mistaken for an unexamined oversight.
- Heavyweight views are `React.lazy` with honest contextual `Suspense` labels;
  never a generic spinner, never a fake progress percentage.

## 8. Enforcement

- `design-system.test.ts` — token layer, component classes, the fabrication
  guard (bans 100 Hz claims, confidence values, solver branding, publish/
  sign-off controls, non-existent channels, causal-graph labels).
- `impeccable detect` — 0 findings on `apps/web/src` (side-tab borders and
  width-transitions removed; epistemic chips use the dot language).
- View test suites pin behavior: flagship stages, palette keyboard, matrix
  scientific structure, lab MODELLED labelling, shell IA.
- `provenance-vocabulary.test.ts` — provenance vocabulary completeness, chain
  translation, and the source scan that bans internal layer codes from the UI.
