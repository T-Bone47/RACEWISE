# RACEWISE — DESIGN SYSTEM

Bespoke visual language for the RACEWISE engineering investigation workspace.
Informed by the taste-skill anti-slop framework (anti-default thinking, shape /
color consistency locks, interaction-state completeness) but adapted for a
**dense engineering product**, not a marketing site.

**Design read:** a high-density F1 race-engineering workstation for engineers
and analysts — pit-wall instrumentation, not SaaS dashboard, not a landing page.

## Dials

| dial | value | meaning here |
|---|---|---|
| DESIGN_VARIANCE | 7 | authored composition (asymmetric command-center hero, split workspace), but analytical clarity always wins |
| MOTION_INTENSITY | 5 | motion communicates state change only (§Motion) |
| VISUAL_DENSITY | 8 | dense tables and ledgers, structured by hierarchy — never by tiny text |

## Identity

- **Accent (locked, one):** `--accent #e10600` (F1 red) — fills, borders,
  active rail. Small accent **text** uses `--accent-bright #ff2b1f` (AA).
- **Neutrals:** cool graphite scale (`#0a0c10` → `#1c2130`), one family.
- **Semantic colors are earned, never decorative:** green = supported/validated,
  amber = partial/uncertain, red = contradiction/failed, blue = analytical,
  violet = modelled. The UI may never imply a state the backend did not emit.
- **Fonts:** Geist Variable (UI) · Geist Mono Variable (numerics, IDs, hashes,
  kbd) with `font-variant-numeric: tabular-nums` on tables so engineering
  values align. Monospace is scoped — never body text.

## Typography levels

| level | class | usage |
|---|---|---|
| 1 | `.t-h1` 15px/650 | investigation / page title |
| 2 | `.t-h2` 13px/620 | primary engineering conclusion |
| 3 | `.t-h3` 12px/600 | hypothesis / analytical category |
| 4–5 | `.t-label` 10.5px caps | section labels, metadata |
| 6 | `.t-num` | telemetry values, deltas, hashes |
| 7 | `.t-annotation` 11.5px | supporting notes |

## Surfaces (three levels only)

| level | token | usage |
|---|---|---|
| 0 | `--surface-0` | application background |
| 1 | `--surface-1` | header, sidebar, major sections |
| 2 | `--surface-2` | elevated/interactive: drawers, palette, inputs |

Group with alignment, spacing, and `--line-soft` dividers before adding another
card. Shadows exist only on drawers/palette and are tinted to the background hue.

## Shape system (consistency lock)

- `--radius 8px` — panels, sections, drawers, palette
- `--radius-sm 5px` — micro-elements: kbd, inline code, evidence tags, bars
- `--radius-pill 999px` — chips, steps, status badges, `ef-badge`s
Mixed systems must follow this documented rule; no stray radii.

## Motion

| scope | token | range |
|---|---|---|
| micro (hover, chips) | `--speed` 150ms | 100–220ms |
| panels, drawers | `--speed-panel` 240ms | 180–350ms |
| major view transitions | `--speed-view` 320ms | 250–500ms |
| easing | `--ease` cubic-bezier(0.22, 0.61, 0.36, 1) | |

Rules: every animation must communicate hierarchy, feedback, or state change;
no ambient loops, no decorative spinners (structural skeletons instead);
tactile press = `translateY(1px)`; everything collapses under
`prefers-reduced-motion`.

## Layering

content → `--z-drawer 60` → `--z-palette 70`. Focus rings: `:focus-visible`
2px `--info` outline.

## Status semantics

States come from the backend and render as `ef-badge st-*` chips: text label
(always) + color + border shape. `MODELLED` is additionally dashed-bordered —
historical fact and modelled result must never look alike. No confidence
scores, no rankings, no "better/worse" anywhere.

## Loading / empty / error

- Loading: `WorkspaceSkeleton` mirrors the real header/ledger/trace layout;
  shimmer only. Context labels ("Collecting evidence…") via `role=status`.
- Empty: explain why and what to do ("No investigation selected…"); recents
  start empty and never fabricate history.
- Errors: structured code + message + scope; backend detail preserved; no
  stack traces.

## Responsive

- >1024px: full workstation (216px rail + workspace)
- 641–1024px: 56px icon rail, quick-grid 2-up, drawers capped
- ≤640px: single-focus stack; nav becomes a horizontal scroll rail;
  tables and `.controls` scroll inside their section (no page overflow);
  drawers full-width. Shell height: `100dvh`, never `h-screen`.

## Accessibility

WCAG AA text contrast everywhere (muted/faint tokens tuned ≥4.5:1; verified
programmatically). Color never the sole signal. Full keyboard support:
Ctrl/Cmd+K palette (↑↓/Enter/Esc), Esc drawers, focus-visible rings,
semantic buttons, `aria-current` nav, `aria-modal` dialogs.

## Icon system

Tabler (`@tabler/icons-react`) — one professional family, 16px/1.75 stroke,
`aria-hidden` decorative use only. No emoji as functional UI; the only
allowed glyph is the physics symbol `Δ` inside the modelled-delta chip
(typography, not iconography).

## Anti-patterns (banned here)

AI-purple/glow · glassmorphism · KPI tile soup · three equal cards ·
confidence meters · ranked hypotheses · decorative spinners · rainbow charts ·
giant marketing heroes · placeholder-as-label · pure-black shadows ·
mixed radius systems · fake telemetry or fake status.
