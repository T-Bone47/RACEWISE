# RACEWISE Workspace Architecture

**How the frontend is composed, how data flows, and who owns what.**
The frontend PRESENTS / NAVIGATES / FILTERS / EXPLORES / CONNECTS / VISUALIZES /
DISCLOSES / TRACES. The backend CALCULATES / VALIDATES / CLASSIFIES / FALSIFIES /
MODELS / PROVIDES PROVENANCE / REPLAYS. No engineering value is computed in React.

---

## 1. App shell

```
App.tsx
├── shell-header   brand · scope crumb · ⌘K trigger · zen-exit (focus mode)
├── shell-sidebar  NAV: Investigation / Knowledge / Analysis / Data / Workspace
├── shell-workspace  one <View> at a time (hash routing, deep-linkable)
├── shell-statusbar  real engine reachability (live /api/health probe)
└── overlay > CommandPalette  (grouped commands + scope actions + typed search)
```

- **Routing:** hash-based (`#/view?params`); the params ARE the scope — every
  analytical view reads its scope from the route, so links, palette actions
  and recents all deep-link reproducibly.
- **Focus mode:** `Ctrl/Cmd+Shift+F` toggles `shell.zen` — sidebar and status
  bar hide, header collapses; the palette also exposes it as a command.
- **Keyboard:** `⌘/Ctrl+K` palette · `Esc` closes overlays · ↑↓/Enter in the
  palette span every entry (commands and search results).

## 2. Flagship workstation (InvestigationView)

```
InvestigationView
├── inv-hero           question (26px) · actions · ContextStrip ·
│                      observation band (metric strip) · inv-meta
├── inv-controls       one structured scope form (real params)
└── inv-workstation
    ├── stage-rail     7 stages, real per-stage statuses, ↑/↓ navigation
    └── stage-center   ONE stage at a time + persistent trace strip
        ├── Observation   TelemetryDeltaPanel (SpeedProfileCanvas) + 6G degradation
        ├── Hypotheses     hyp-row list → click opens the inspector drawer
        ├── Evidence       ledger table (EFFECT column) + preserved conflicts
        ├── Falsification  gate banner + rule
        ├── Counterfactual candidates + MODELLED results
        ├── Synthesis      engineering report + residual callout + actions
        └── Verification   graph + replay + memory (scope-addressed)
ContextInspector (right column; fixed drawer ≤1280px)
```

**State ownership** (all in `InvestigationView`; panels stay presentational):

| State | Purpose | Set by |
|---|---|---|
| `result` | the verbatim 6N payload | `run()` from `/api/catalog/engineering-investigation` |
| `stage` | which center panel is visible | the stage rail (default Observation) |
| `inspector`/`inspectorHistory` | right-drawer entries (evidence / hypothesis / provenance) with a back stack | row clicks, trace-to-source |
| `hypFilter` / `focusNode` | evidence filter + graph focus (one shared selection) | hypothesis/evidence clicks |
| `openTrace` | expanded bottom-strip node | trace strip |
| canvas `view`/`drag` | display-only zoom/region (inside `SpeedProfileCanvas`, reset on payload change) | chart controls |

## 3. The signature interaction (Telemetry ↔ Evidence ↔ Hypothesis)

- **Windows ↔ canvas:** the comparison engine's loss windows are rendered as
  time-axis bands on the canvas; hovering a window row highlights its band —
  the one evidence class that carries real time geometry.
- **Cursor ↔ readout:** the crosshair HUD reads measured target/reference
  speeds and Δv at the hovered index (payload values, no math).
- **Hypothesis ↔ evidence:** selecting a hypothesis opens the drawer with its
  supporting/contradicting/non-decisive evidence; every chip drills into the
  evidence entry in the same drawer (back-stack returns).
- **Evidence ↔ trace:** every trace strip node and drawer claim links to the
  evidence ids it rests on.
- The engine computes all relations; the frontend only highlights payload
  links — it never derives a new connection.

## 4. Data-flow conventions

1. Every fetch is scope-keyed, effect-guarded (`cancelled` flags), and
   cancelled on unmount. No polling, no global cache duplication.
2. Panels that need sibling-scope data re-fetch from the real endpoint with
   the same params (e.g. `stint-evidence`, `attribution`, identity-fraction
   counterfactual for the canvas) — never from a copied value.
3. Component tests mock `fetch` at the route level; the payload fixtures
   mirror the real API shapes (`test-utils.ts`).
4. Honest states (`UNAVAILABLE`, `INSUFFICIENT_EVIDENCE`, …) render via
   `StatePanel`/`StructuredError` — never as empty space or fake data.

## 5. Component inventory & reuse rules

See `docs/RACEWISE_DESIGN_SYSTEM.md` §3 for the full RWS table. Rules:

- One inspector (`ContextInspector`), one drawer body per kind
  (`EvidenceDetails`, `HypothesisDetails`, `ProvenanceDetails`) — no
  per-view duplicates.
- One chart voice (`SpeedProfileCanvas` + `.tv-*` classes); view-specific
  charts reuse the same axis/grid/legend conventions.
- One states voice (`StatePanel`), one error voice (`StructuredError`).
- New UI consumes the token layer and these primitives; introducing a
  parallel `*Card`, `*Drawer` or `*State` variant is a review flag.

## 6. Responsive contract

| Width | Behavior |
|---|---|
| ≥1280 | full workstation; sticky inspector column |
| 1024–1280 | rail → horizontal stage chips; inspector → fixed drawer |
| 768–1024 | single column; report grid stacks |
| ≤768 | loop-order stack; metric strip 2-col |

## 7. Verification map

| Surface | Covered by |
|---|---|
| Shell IA, focus mode, palette shortcut | `app-shell.test.tsx` |
| Flagship stages, drawer, EFFECT column, honest states | `investigation-workspace.test.tsx` |
| Falsification scientific structure | `falsification-matrix.test.tsx` |
| Lab MODELLED discipline | `counterfactual-lab.test.tsx` |
| Command center (hero, templates, console, ledger) | `command-center.test.tsx` |
| Tokens + fabrication guard | `design-system.test.ts` |
| Detector (AI-tell scan) | `impeccable detect` — 0 findings |
| Live API + determinism | `tests/integration` (backend) + the 12-point live smoke |
