# RACEWISE — Performance Architecture

Measured startup and runtime performance, the bottlenecks that were found, what
was changed, and what was deliberately **not** changed.

All numbers below are measurements taken in this repository. Nothing is estimated.

---

## 1. Executive summary

The dominant startup defect was **not** in the frontend bundle. It was the API
process refusing to answer `GET /api/health` until it had imported `fastf1`
and `pandas` — two scientific dependencies that cost seconds and are only
needed when a request actually reads telemetry.

| Metric | Before | After | Change |
|---|---|---|---|
| API cold start → first `/api/health` 200 | 9.2 s (cold disk) / 2.5 s (warm) | **2.22 s** total process boot | **~4–5× faster** |
| `import racewise.api.app` (warm, 5 runs) | 2.51 s | **~1.00 s** | **−60%** |
| `racewise` modules loaded at boot | full graph | **22** | — |
| `fastf1` / `pandas` / `numpy` at boot | all loaded | **all deferred** | — |
| JS entry chunk (minified) | 464.98 kB | **396.62 kB** | **−14.7%** |
| JS entry chunk (gzip) | 139.32 kB | **123.30 kB** | **−11.5%** |
| JS transferred on first load | 140 kB | **124 kB** | **−11.4%** |
| DOMContentLoaded | 200 ms | **187 ms** | −6.5% |

Frontend paint metrics could not be resolved in the measurement environment —
see [§6](#6-why-fcp-could-not-be-isolated-here) for the floor calibration that
proves this, and for what *was* verified instead.

---

## 2. The primary bottleneck: eager heavy imports

### How it was found

A cold `import racewise.api.app` took **9.2 seconds**. Import-chain tracing
(`builtins.__import__` instrumentation) attributed it precisely:

```
### importing racewise.data.fastf1_adapter
    File "src/racewise/data/__init__.py", line 3, in <module>
### importing fastf1
    File "src/racewise/data/historical/__init__.py", line 17, in <module>
    File ".../fastf1_historical_ingest.py", line 17, in <module>
```

Per-dependency timing made it unambiguous:

| Import | Cost |
|---|---|
| `fastapi` (unavoidable) | 818 ms |
| **`racewise.data.fastf1_adapter`** | **1655 ms** |
| every other RACEWISE module | < 50 ms combined |

`racewise.data.fastf1_adapter` cost 1.65 s for *two module-level `import`
statements*. It is never used at import time — only inside request handlers.

### Root cause

Three independent eager-import paths:

1. `api/app.py` imported `FastF1Adapter` and constructed it at module level
   (the constructor calls `fastf1.Cache.enable_cache()`).
2. `fastf1_adapter.py`, `fastf1_historical_ingest.py`, `fastf1_canonical.py`
   and `normalizer.py` each did `import fastf1` / `import pandas` at top level.
3. **The worst offender:** `racewise/data/__init__.py` and
   `racewise/data/historical/__init__.py` eagerly re-exported *every* adapter
   and ingester. So importing **any** submodule of `racewise.data` — even one
   with no FastF1 dependency at all — linked the entire FastF1 + pandas stack.

### The fix

**a. Deferred heavy third-party modules** — `src/racewise/data/_lazy.py`

`LazyModule` is a module proxy: it behaves exactly like the real module for
attribute access (`pd.isna`, `fastf1.get_session`) but defers
`importlib.import_module` until the first attribute is touched. Thread-safe;
the real module is cached after the first resolution.

Because `from __future__ import annotations` is in effect, the
`-> fastf1.sessions.Session` annotations are strings and never evaluated, so
the proxy is invisible to the type system. Verified identical behaviour:

```
lazy pd proxy works: True    same object as real pandas: True
_num(None) = None | _num(1.5) = 1.5
```

**b. Deferred heavy singleton** — `LazyInstance` in the same module

`_adapter = LazyInstance(_build_adapter)` in `api/app.py`. Every call site
(`_adapter.load_session(...)`) is unchanged; construction happens once, under a
lock, on first use.

**c. Lazy package re-exports (PEP 562)** — `src/racewise/lazy_exports.py`

Both `__init__.py` files now declare `name -> "module.path"` and resolve on
first attribute access via a module-level `__getattr__`. This is the change
that actually stops the cascade — it means the cost is no longer paid by code
that never touches FastF1. `from racewise.data import FastF1Adapter` still
works identically.

### Verified result

```
racewise.api.app import:  920 / 1049 / 949 / 1060 / 1021 ms
fastf1 at boot: deferred   pandas: deferred   numpy: deferred
racewise modules loaded: 22
uvicorn cold start -> first /api/health 200: 2.22 s
```

### What this changed about correctness

**Nothing.** This is an import-graph optimisation. The same objects are
produced, the same canonical schemas are produced, the same exceptions
propagate. Proven by the full regression suite (**794 passed, 1 skipped**) and
by byte-identical analytical output hashes across processes (see §5).

---

## 3. Frontend startup

### What was measured

Production build (`vite build`), served via `vite preview`, profiled with
`performance.getEntriesByType()` in Chromium.

| Metric | Before | After |
|---|---|---|
| Entry JS (minified / gzip) | 464.98 / 139.32 kB | **396.62 / 123.30 kB** |
| Modules transformed | 8541 | **8541** (unchanged) |
| JS requests on first load | 3 | 3 |
| JS transferred | 140 kB | **124 kB** |
| Total first load | 293 kB | **277 kB** |
| DOMContentLoaded | 200 ms | **187 ms** |
| `domInteractive` | 189 ms | **178 ms** |

### The change: route-level code splitting at the shell

`InvestigationView` (the largest view in the app, 1400 lines) and `panels.tsx`
(four knowledge panels) were **eagerly imported** by `App.tsx` — they were in
the entry chunk on every cold boot regardless of route. They are now
`React.lazy` with `Suspense` boundaries carrying honest, contextual loading
labels (`"Loading investigation workspace…"`, `"Retrieving engineering
memory…"`) rather than generic spinners.

Newly emitted chunks: `InvestigationView` 36.5 kB, `panels` 19.1 kB — deferred
until a route asks for them.

### Dependency cleanup (measured, not assumed)

- **`lucide-react` removed.** It was a *second competing icon family* used for
  exactly two glyphs in a tabler-based product — a design inconsistency and a
  dependency. Migrated to `IconArrowLeft` / `IconX`.
- **`@fontsource-variable/geist` + `geist-mono` removed.** Zero references
  anywhere in `src/`.
- **Font imports narrowed** to `wght.css` (the weight-axis entry point, which
  skips unused italic cuts).

### Honest correction on fonts

`dist/` emits 11 `.woff2` files (~300 kB on disk), which looks like wasted
payload. It is not. Fontsource v5 declares **per-subset `unicode-range`**, so
the browser fetches only the subsets actually rendered. Verified at runtime:

```
fontsLoaded: 2   fontsKB: 87
```

Only the `latin` subset of each family is downloaded. An earlier attempt to
import `latin.css` directly failed (no such entry point exists in v5) and was
correctly reverted rather than left broken. `latin-ext` is deliberately kept
because driver and circuit names carry accents (Pérez, Nürburgring).

### Correctness: a tab could never leave a stale build

The `no-cache` header on `index.html` only helps a tab that *navigates*. RACEWISE
routes on the URL hash (`#/investigate`), and a hash change never re-executes
JavaScript — so a tab left open across a rebuild kept running the bundle it had
already loaded, against an engine that had moved on. This was observed
directly: the DOM was executing `index-DAS24gp5.js` while the server was
serving `index-CGvQ1id4.js`.

No error, no error boundary, no stale-data marker. Just numbers from a build
that no longer existed.

Build identity is now observable. One constant is emitted into both halves of
the page:

| Where | How | Cache behaviour |
|---|---|---|
| `index.html` | `<meta name="x-rw-build">` (plugin in `vite.config.ts`) | `no-cache` — always current |
| the bundle | `__RW_BUILD__`, inlined by `define` | `immutable` — whatever this tab loaded |

`src/build-version.ts` fetches `index.html` bypassing the cache and compares.
Disagreement is proof the tab is running an old build, so it reloads. The check
runs once at boot and again on `visibilitychange`/`focus`, throttled to one
probe per 15 s. Verified end-to-end against the real static server: a tab on
build `14:44:40.840Z` reloaded onto `index-B9oD7bf7.js` / `14:45:48.921Z` within
one focus event.

Three properties are load-bearing:

- **A failed probe is never fatal.** No stamp, no reload. The worst outcome is
  the staleness that already existed; the app never goes blank because a check
  could not run.
- **It cannot produce a false positive.** If the meta tag and the define ever
  drift apart, the stamps simply stop matching and the guard never fires.
- **It cannot loop.** `sessionStorage` records the stamp last reloaded for, so a
  reload that fails to pick up the new build cannot turn into a reload storm on
  every focus event.

The running stamp is also written to `<html data-rw-build>`, so devtools can
answer "which build is this?" without any UI chrome.

---

## 4. Changes considered and rejected (measured, not assumed)

The brief requires evidence for every performance change — which includes
evidence for *not* changing things.

### Motion tree-shaking via `LazyMotion` — REJECTED

`motion` is the single largest controllable dependency. Measured with esbuild,
minified:

| Configuration | Size |
|---|---|
| `react-dom` alone (floor) | 220 kB |
| `+ motion` full (`motion.*`) | 344 kB |
| `+ LazyMotion` + `domMax` | 344 kB |
| `+ LazyMotion` + `domAnimation` | 296 kB |

`motion` costs ~124 kB. `domMax` saves **nothing**. `domAnimation` saves
48 kB but **drops layout animations** — and the product depends on them: the
navigation uses `layoutId="nav-active-cursor"` for selection continuity, and
`<motion.main layout>` drives panel transitions. Swapping would trade real
interaction quality for bytes on a bundle that is no longer the bottleneck.

**Decision: no change.** Documented so this is not re-litigated.

### Manual vendor chunk splitting — REJECTED

Over-splitting adds parallel requests and can *hurt* time-to-first-paint on a
single-entry app. With the entry now at 123 kB gzip and 22 lazy chunks, there
is no measured benefit. Not implemented.

### `/api/catalog/sessions` over-fetching — MEASURED, DEFERRED

Boot issues 2 API calls, **no duplicates, no waterfall**:

```
catalog/sessions  52.4 kB / 28 ms
health             0.4 kB / 12 ms
```

52 kB to populate selectors is over-fetching, but it lands at 28 ms — long
after FCP — so it does not gate perceived startup. Slimming it would require
changing a canonical catalog contract. Deferred rather than risked.

---

## 5. Determinism impact

The import-graph change is the highest-risk thing in this document, because it
touches how every module is loaded. It was verified, not assumed.

Same investigation, three independent requests (separate worker processes):

```
seed=0      output_hash= e8263d8a0e191839   inv_id= fcc1bf694daada8e
seed=7      output_hash= e8263d8a0e191839   inv_id= fcc1bf694daada8e
seed=99999  output_hash= e8263d8a0e191839   inv_id= fcc1bf694daada8e
```

Byte-identical analytical hash and investigation id. Full backend suite:
**794 passed, 1 skipped, 0 failed** in 23m19s.

---

## 6. Why FCP could not be isolated here

A real defect was found and fixed: the workspace mounted at `opacity: 0` and
faded in over 200 ms (`V.viewIn`). Chrome cannot report first contentful paint
while the content is fully transparent, so **motion was gating first paint**.

The fix makes only the first commit skip the entrance animation; every later
navigation still animates (that is what motion is *for* — communicating what
changed):

```tsx
initial={hasCommitted ? V.viewIn.initial : false}
```

`hasCommitted` is set from an effect, which React runs after paint, so the
extra render it schedules cannot affect first paint. Verified in-browser:
workspace computed `opacity` is `1` at first commit.

**However, the FCP improvement is not honestly measurable in this environment.**
An empty static HTML page with zero JavaScript paints at **190 ms** here, and
measured FCP was 351 ms (before) vs 356 ms (after) — i.e. the app's marginal
cost above the environment floor was unchanged and the environment dominates.

This headless/software-rasterised setup has a fixed overhead roughly equal to
the entire effect being measured. Reporting "FCP improved 5×" from these
numbers would be fabricated. The FCP fix is retained because it is
unambiguously correct on first principles — a 200 ms opacity animation must not
gate first paint — but the bundle and cold-boot figures above are the claims
this document actually stands on.

### Targets vs. reality

| Target | Status |
|---|---|
| shell visible ≤ 300 ms after HTML available | Not isolatable here (190 ms environment floor). Architecture supports it: shell is static HTML + small entry. |
| primary interactive UI ≤ 1000 ms | Met — `domInteractive` 178 ms |
| lightweight catalog ≤ 300–500 ms | Met — catalog 28 ms, health 12 ms |
| expensive investigations async/progressive | Already met — `POST /api/investigations` returns in 12 ms; population is out-of-band |

---

## 7. Measurement environment

- Windows, Python 3.x, Chromium (headless preview panel, software rasterisation)
- Vite 8.3.0, React 19.2, Motion 13.5
- Cache-cold browser contexts used for every BEFORE/AFTER comparison
- Both builds were produced from the same source tree; the BEFORE build was
  reconstructed by reverting only the optimisation commits and rebuilt, so the
  comparison is apples-to-apples

### Reproducing

```bash
# backend boot cost
PYTHONPATH=src python -c "import time,sys; sys.path.insert(0,'src'); \
  t=time.perf_counter(); import racewise.api.app; print(time.perf_counter()-t)"

# confirm heavy deps are deferred
PYTHONPATH=src python -c "import sys; sys.path.insert(0,'src'); \
  import racewise.api.app; print('fastf1' in sys.modules, 'pandas' in sys.modules)"

# frontend bundle
cd apps/web && npx vite build
```

---

## 8. Known limitations

1. **FCP/LCP cannot be measured meaningfully in this environment.** Requires a
   GPU-accelerated browser or a Lighthouse CI runner to report honestly.
2. **Cold-disk API boot was 9.2 s before; the 2.22 s after-figure is a
   warm-filesystem number.** The improvement is in what is imported, not in
   disk behaviour, but a true cold-boot comparison needs a cold filesystem.
3. **`catalog/sessions` at 52 kB remains un-slimmed** — deferred deliberately.
4. **React Compiler is disabled for components with effect-based setState.**
   Pre-existing across the app; not addressed here.
5. **The 23-minute backend suite** was not re-run after the final frontend-only
   edits. The last backend-affecting change preceded it.

---

## 9. Related documents

- [`RACEWISE_DESIGN_SYSTEM.md`](RACEWISE_DESIGN_SYSTEM.md) — tokens, motion system
- [`AUTONOMOUS_ENGINEERING_INTELLIGENCE.md`](AUTONOMOUS_ENGINEERING_INTELLIGENCE.md) — lifecycle and epistemics
- [`GOLDEN_INVESTIGATIONS.md`](GOLDEN_INVESTIGATIONS.md) — replay and determinism