# Stitch UI/UX Integration — Implementation Notes

Source: `stitch_racewise_telemetry_investigation_platform.zip` (Stitch /
Figma export). The ZIP contains 6 screens (`code.html` + `screen.png` each)
and one `DESIGN.md` design-system spec under
`telemetry_investigation_workbench/`.

## 1. What was adopted from Stitch

### Design tokens (Stitch `DESIGN.md` → `apps/web/src/App.css`)

The full Stitch surface ladder, signal accents, epistemic palette,
typography and geometry are implemented as CSS variables:

- **Surfaces (Layer 0–3):** `--st-canvas #0b0e12` · `--st-recessed #0e1014` ·
  `--st-surface #111418` · `--st-element #171b22` · `--st-hover #1e232c`
- **Structural lines:** `--st-line #232934` · `--st-line-hi #2f3746`
- **Signal accents:** `--st-primary #00e5ff` (cyan) · `--st-secondary #3875ff`
  (indigo), with AA-safe text variants (`--st-primary-text`, `--st-secondary-text`,
  `--st-error`)
- **Epistemic state engine:** `--ep-fact/--ep-calc/--ep-infer/--ep-cf/--ep-assume`
  plus verification colors (SUPPORTED green, CONTRADICTED red, …)
- **Typography:** Inter (narrative) + JetBrains Mono (all metrics, tabular)
  via `@fontsource-variable/inter` and `@fontsource-variable/jetbrains-mono`
- **Geometry:** structural panels `0px` radius, interactive elements `4px`;
  pills prohibited per the Stitch spec
- **Elevation:** tonal stepping + hairline borders; Layer-4 overlays use the
  hard-edged `--st-shadow-overlay`

Every pre-existing token (`--bg`, `--panel`, `--accent`, `--radius`, …) is
**aliased by reference** to the Stitch layer, so all 17 views adopted the new
design without selector churn. A design-system contract test pins this.

### Component language

- Epistemic chips (`.ef-badge`, `.claim-tag`, `.gp-node`) restyled to the
  Stitch badge structure: mono uppercase microtype, status color at 8–16% bg,
  2px left status border.
- Tables: 1px hairline rules, mono uppercase headers, tabular numerals.
- Buttons: primary = cyan @10% fill + cyan border (Stitch spec), secondary =
  element surface + hairline.
- Palette/overlay: Layer-4 surface with the Stitch shadow.

## 2. Stitch screens → RACEWISE production routes

| Stitch screen | Production surface |
| --- | --- |
| Engineering Command Center | `#/command` (CommandCenterView) — query console, launcher, real system status |
| Active Investigation Workspace (v1–v3) | `#/autonomous` (AutonomousView) + flagship hero upgrades in `#/investigate` (InvestigationView) |
| Falsification Matrix | `#/falsification` — new route mapping to the real hypothesis-evaluation investigation (H1–H6 + falsification gate); no mock |
| Counterfactual Lab | `#/counterfactual` (CounterfactualView, real simulation) |
| Navigation Deck (sidebar) | App shell sidebar with Stitch vocabulary: Active Investigation, Falsification Matrix, Sessions & Drivers, Counterfactual Lab, Regime Timeline |

### Flagship upgrades (InvestigationView)

- **Hero question** (`.inv-hero .inv-question`): the investigation question is
  the dominant element (22px, Inter, −0.02em), with the run id and conclusion
  state chip beside it.
- **Metric strip** (`.metric-strip`): evidence items, hypotheses tested,
  preserved contradictions, counterfactuals, unresolved — every cell derived
  from the real engine result, never fabricated.
- **Phase timeline** (`.phase-timeline`): deterministic chain phases derived
  from actual result content (Evidence phase shows done only when the ledger
  is non-empty, etc.).
- **Telemetry ↔ evidence interaction (§10):** a real telemetry-deltas panel
  (from `/api/catalog/telemetry-comparison/{season}/{round}?driver_a=…&driver_b=…&lap=…`)
  for the same canonical scope. Hovering the panel highlights
  telemetry-sourced evidence rows (`.catalog-table tr.linked`) — the
  relationship is real (same 6E/6F source phases, same scope), not invented
  per-window mapping.
- **Export / Copy ID:** Export writes the verbatim engine JSON; Copy ID uses
  the Clipboard API with an execCommand fallback (feedback reflects the real
  outcome).

### Command palette

Extracted to `apps/web/src/CommandPalette.tsx` (testable). Commands include
New Investigation, Open Active Investigation, Falsification Matrix, Graph,
Memory, Replay, Counterfactual Lab, etc. — every command navigates a real
route. Structured search (`/api/catalog/search`) integrated. **Fixed a real
pre-existing defect: palette content previously rendered without the
`.palette` Layer-4 surface wrapper (unstyled on the backdrop).** A
regression test pins the wrapper.

## 3. What was deliberately NOT adopted

- Tailwind CDN / generated utility classes — the existing tokens-only CSS
  architecture is kept (maintainability mandate §23).
- Material Symbols webfont + Google-hosted assets — existing tabler/lucide
  icon families kept; no external font/CDN dependency added to production.
- All mock content from the prototype screens (fake investigators
  "Dr. H. Vance", fake ids `INV-2023-01-57B`, fake telemetry numbers,
  fake confidence percentages). Production UI renders only API data; where
  the prototype shows a number RACEWISE shows the real engine value or an
  honest empty state.

## 4. Preserved functionality checklist

All pre-existing views and routes remain: command center, autonomous
investigation, investigation workspace, graph (build/path/trace), replay,
compare, memory (+ related), catalog, telemetry, attribution, fusion, stint,
race gap, counterfactual, envelope, regimes, patterns, pattern evidence.
Hash routes are unchanged (`#/investigate?…` deep links incl.
`investigation_id` addressing). Backend untouched — zero API changes.

## 5. Tests

- `apps/web/src/design-system.test.ts` (vitest): 12 tests pinning the Stitch
  token layer (surface ladder, accents, epistemic palette, legacy aliasing,
  no F1-red remnants, geometry, fonts, reduced-motion) and flagship
  component classes (hero, metric strip, phase timeline, `tr.linked`
  cross-highlight, orchestrator-vs-engine distinction).
- Run: `npm --prefix apps/web test` (vitest, jsdom).
- Frontend build (`tsc -b && vite build`) type-checks everything.
