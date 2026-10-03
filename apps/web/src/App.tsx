import { Suspense, lazy, useCallback, useEffect, useState } from 'react'
import {
  IconGauge, IconSearch, IconGraph, IconHistory, IconGitCompare, IconArrowsExchange, IconReload,
  IconDatabase, IconActivity, IconChartBar, IconChartLine, IconStack2,
  IconBoxMultiple, IconChartHistogram, IconListNumbers, IconMathFunction, IconTable,
} from '@tabler/icons-react'
/* Fontsource declares per-subset unicode-range, so the browser only fetches
   the subsets the rendered glyphs actually need (latin / latin-ext for this
   UI). `wght.css` is the weight-axis entry point and skips the italic cuts,
   which this workstation never uses. */
import '@fontsource-variable/inter/wght.css'
import '@fontsource-variable/jetbrains-mono/wght.css'
import './App.css'
import './design-system.css'
import { MotionConfig, motion } from 'motion/react'
import { T, V } from './motion'
import CommandCenterView from './CommandCenterView'
import CommandPalette from './CommandPalette'
import { LoadingLine } from './workspace'

/* Startup budget: the entry chunk carries the shell + the landing Command
   Center only. InvestigationView (the largest view in the app) and the four
   knowledge panels are deferred until a route actually asks for them, so a
   cold boot parses a fraction of the previous JavaScript. */
const InvestigationView = lazy(() => import('./InvestigationView'))
const GraphPanel = lazy(() => import('./panels').then((m) => ({ default: m.GraphPanel })))
const ReplayPanel = lazy(() => import('./panels').then((m) => ({ default: m.ReplayPanel })))
const ComparePanel = lazy(() => import('./panels').then((m) => ({ default: m.ComparePanel })))
const MemoryPanel = lazy(() => import('./panels').then((m) => ({ default: m.MemoryPanel })))

/* Route-level chunk prefetch.
 *
 * A click should never pay for a network round trip the user could have
 * triggered a moment earlier. Hovering or focusing a destination is an
 * unambiguous intent signal, so the chunk is requested then — by the time the
 * click lands the module is already parsed and the route paints immediately.
 * Combined with immutable caching on hashed assets, repeat visits cost zero
 * network and the route is synchronous. */
const ROUTE_LOADERS: Partial<Record<ViewId, () => Promise<unknown>>> = {
  investigate: () => import('./InvestigationView'),
  autonomous: () => import('./AutonomousView'),
  falsification: () => import('./FalsificationMatrixView'),
  counterfactual: () => import('./CounterfactualView'),
  catalog: () => import('./CatalogExplorer'),
  telemetry: () => import('./TelemetryView'),
  attribution: () => import('./AttributionView'),
  fusion: () => import('./EvidenceFusionView'),
  stint: () => import('./StintEvidenceView'),
  racegap: () => import('./RaceGapView'),
  envelope: () => import('./PerformanceEnvelopeView'),
  regime: () => import('./PerformanceRegimeView'),
  patterns: () => import('./PerformancePatternView'),
  patternevidence: () => import('./PatternEvidenceView'),
  graph: () => import('./panels'),
  replay: () => import('./panels'),
  compare: () => import('./panels'),
  memory: () => import('./panels'),
}

const prefetched = new Set<ViewId>()
function prefetchRoute(id: ViewId) {
  if (prefetched.has(id)) return
  const loader = ROUTE_LOADERS[id]
  if (!loader) return
  prefetched.add(id)
  // fire and forget; a failed prefetch must never surface to the user
  loader().catch(() => prefetched.delete(id))
}

const CatalogExplorer = lazy(() => import('./CatalogExplorer'))
const TelemetryView = lazy(() => import('./TelemetryView'))
const AttributionView = lazy(() => import('./AttributionView'))
const EvidenceFusionView = lazy(() => import('./EvidenceFusionView'))
const StintEvidenceView = lazy(() => import('./StintEvidenceView'))
const RaceGapView = lazy(() => import('./RaceGapView'))
const CounterfactualView = lazy(() => import('./CounterfactualView'))
const FalsificationMatrixView = lazy(() => import('./FalsificationMatrixView'))
const PerformanceEnvelopeView = lazy(() => import('./PerformanceEnvelopeView'))
const PerformanceRegimeView = lazy(() => import('./PerformanceRegimeView'))
const PerformancePatternView = lazy(() => import('./PerformancePatternView'))
const PatternEvidenceView = lazy(() => import('./PatternEvidenceView'))
const AutonomousView = lazy(() => import('./AutonomousView'))

/* ============ Phase 6Q — application shell ============ */

type ViewId =
  | 'command' | 'autonomous' | 'investigate' | 'falsification' | 'graph' | 'replay' | 'compare' | 'memory'
  | 'catalog' | 'telemetry' | 'attribution' | 'fusion' | 'stint'
  | 'racegap' | 'counterfactual' | 'envelope' | 'regime' | 'patterns'
  | 'patternevidence' | 'legacy'

/* one professional icon family (tabler) — no emoji as functional UI.
   Navigation IA (mission §7): grouped by workflow stage — INVESTIGATION,
   KNOWLEDGE, ANALYSIS, DATA, WORKSPACE — every existing route preserved. */
const NAV: Array<{ group: string; items: Array<{ id: ViewId; label: string; icon: typeof IconGauge }> }> = [
  {
    group: 'Investigation',
    items: [
      { id: 'command', label: 'Command Center', icon: IconGauge },
      { id: 'investigate', label: 'Active Investigation', icon: IconSearch },
      { id: 'falsification', label: 'Falsification', icon: IconListNumbers },
      { id: 'counterfactual', label: 'Counterfactual Lab', icon: IconBoxMultiple },
    ],
  },
  {
    group: 'Knowledge',
    items: [
      { id: 'graph', label: 'Investigation Graph', icon: IconGraph },
      { id: 'memory', label: 'Engineering Memory', icon: IconHistory },
      { id: 'patterns', label: 'Cross-Race Patterns', icon: IconMathFunction },
      { id: 'patternevidence', label: 'Pattern Evidence', icon: IconTable },
    ],
  },
  {
    group: 'Analysis',
    items: [
      { id: 'telemetry', label: 'Lap Comparison', icon: IconActivity },
      { id: 'attribution', label: 'Lap Attribution', icon: IconChartBar },
      { id: 'fusion', label: 'Evidence Fusion', icon: IconChartLine },
      { id: 'stint', label: 'Stint Analysis', icon: IconStack2 },
      { id: 'racegap', label: 'Race Gap', icon: IconArrowsExchange },
      { id: 'envelope', label: 'Performance Envelope', icon: IconChartHistogram },
      { id: 'regime', label: 'Regime Timeline', icon: IconListNumbers },
    ],
  },
  {
    group: 'Data',
    items: [
      { id: 'catalog', label: 'Sessions & Drivers', icon: IconDatabase },
    ],
  },
  {
    group: 'Workspace',
    items: [
      { id: 'autonomous', label: 'Autonomous Query', icon: IconSearch },
      { id: 'compare', label: 'Compare', icon: IconGitCompare },
      { id: 'replay', label: 'Replay', icon: IconReload },
    ],
  },
]

function defaultScopeParams(): URLSearchParams {
  return new URLSearchParams({
    question_type: 'LAP_PERFORMANCE',
    driver_a: 'max-verstappen',
    driver_b: 'sergio-perez',
    season: '2023',
    round: '1',
    lap_number: '6',
  })
}

function parseHash(): { view: ViewId; params: URLSearchParams } {
  const hash = window.location.hash.replace(/^#\/?/, '')
  const [view, query] = hash.split('?')
  const params = new URLSearchParams(query || '')
  const known = new Set(NAV.flatMap((g) => g.items.map((i) => i.id)))
  const v = (known.has(view as ViewId) ? view : 'command') as ViewId
  return { view: v, params }
}

export default function App() {
  const [{ view, params }, setRoute] = useState(parseHash)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [recentsCount, setRecentsCount] = useState(0)
  /* honest engine status: one real /api/health probe — the bar never claims
     readiness the engine did not confirm (UX audit §16) */
  const [engineUp, setEngineUp] = useState<boolean | null>(null)
  /* analysis focus mode (mission): hide navigation and metadata, maximize
     the analytical workspace — Ctrl/Cmd+Shift+F toggles */
  const [zen, setZen] = useState(false)

  useEffect(() => {
    fetch('/api/health')
      .then((r) => { setEngineUp(r.ok) })
      .catch(() => { setEngineUp(false) })
  }, [])

  useEffect(() => {
    function onHash() {
      setRoute(parseHash())
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const navigate = useCallback((v: string) => {
    if (!v) return
    window.location.hash = `#/${v}`
    setRoute(parseHash())
  }, [])

  /* keyboard: Ctrl/Cmd+K opens the command palette; Ctrl/Cmd+Shift+F
     toggles analysis focus mode */
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPaletteOpen(true)
      }
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'f') {
        e.preventDefault()
        setZen((z) => !z)
      }
      /* Esc closes the palette from anywhere (no keyboard traps, §28) */
      if (e.key === 'Escape') {
        setPaletteOpen(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem('racewise.recent.investigations.v1')
      setRecentsCount(raw ? (JSON.parse(raw) as unknown[]).length : 0)
    } catch {
      setRecentsCount(0)
    }
  }, [view])

  const presetParams = view === 'investigate' && [...params.keys()].length > 0 ? params : undefined

  /* First mount must paint immediately. Fading the workspace in from
     opacity:0 delays the browser's first contentful paint by the length of
     the animation (measured: FCP 893ms with a 200ms fade against a 423ms
     DOMContentLoaded). Motion communicates view *changes*; it must never
     gate the first frame.
     `hasCommitted` is still false during the first render (so the workspace
     paints with no entrance animation) and true for every navigation after
     it. The flag is set from an effect, which React runs after paint, so the
     extra render it schedules cannot affect first paint. */
  const [hasCommitted, setHasCommitted] = useState(false)
  useEffect(() => { setHasCommitted(true) }, [])

  const scopeParams = useCallback(() => {
    if ([...params.keys()].length > 0) return new URLSearchParams(params)
    return defaultScopeParams()
  }, [params])

  return (
    <MotionConfig reducedMotion="user">
    <div className={`shell ${zen ? 'zen' : ''}`}>
      {/* ================= HEADER — Stitch topbar with context crumb ================= */}
      <header className="shell-header">
        <h1>RACE<span>WISE</span></h1>
        <span className="shell-tagline">evidence-driven race engineering</span>
        {[...params.keys()].length > 0 && params.get('season') && (
          <span className="shell-tagline" aria-label="current scope">
            {params.get('season')} R{params.get('round') ?? '·'}
            {params.get('driver_a') ? ` · ${params.get('driver_a')} vs ${params.get('driver_b') ?? '—'}` : ''}
            {params.get('lap_number') ? ` · lap ${params.get('lap_number')}` : ''}
          </span>
        )}
        <span className="spacer" />
        {zen && (
          <button
            className="zen-exit"
            onClick={() => setZen(false)}
            title="Exit focus mode (Ctrl/Cmd+Shift+F)"
          >
            Exit focus
          </button>
        )}
        <button
          className="search-trigger"
          onClick={() => setPaletteOpen(true)}
          aria-label="Open command palette and search"
        >
          <IconSearch size={15} strokeWidth={1.75} aria-hidden="true" />
          <span className="search-hint">Search / commands</span>
          <kbd>Ctrl K</kbd>
        </button>
      </header>

      {/* ================= SIDEBAR — Stitch Navigation Deck ================= */}
      <motion.nav
        className="shell-sidebar"
        aria-label="Workspace navigation"
        animate={{ opacity: zen ? 0 : 1, x: zen ? -6 : 0 }}
        transition={T.panel}
        style={{ pointerEvents: zen ? 'none' : undefined }}
      >
        <button
          className="primary"
          style={{ width: '100%', marginBottom: 10 }}
          onClick={() => navigate('command')}
        >
          + New investigation
        </button>
        {NAV.map((group) => (
          <div key={group.group}>
            <div className="nav-group-label">{group.group}</div>
            {group.items.map((item) => (
              <button
                key={item.id}
                className={`nav-item ${view === item.id ? 'active' : ''}`}
                onClick={() => navigate(item.id)}
                onMouseEnter={() => prefetchRoute(item.id)}
                onFocus={() => prefetchRoute(item.id)}
                aria-current={view === item.id ? 'page' : undefined}
              >
                {view === item.id && (
                  /* instrument cursor: one shared element gliding between
                     destinations (Motion layoutId; disabled under reduced motion) */
                  <motion.span
                    layoutId="nav-active-cursor"
                    className="nav-cursor"
                    aria-hidden="true"
                    transition={T.panelSpring}
                  />
                )}
                <span className="nav-ico" aria-hidden="true"><item.icon size={16} strokeWidth={1.75} /></span>
                <span className="nav-label">{item.label}</span>
              </button>
            ))}
          </div>
        ))}
      </motion.nav>

      {/* ================= WORKSPACE ================= */}
      {/* No `layout` here on purpose. Layout projection measures and animates
          the element's geometry every frame; applied to the whole workspace it
          is the single most expensive Motion operation on the page and it made
          every route change feel sluggish — for zero visual gain, because the
          workspace itself does not resize between routes (only the zen sidebar
          collapse does, and that has its own transition). */}
      <motion.main className="shell-workspace">
        <motion.div
          key={view}
          initial={hasCommitted ? V.viewIn.initial : false}
          animate={V.viewIn.animate}
          transition={T.panel}
        >
        {view === 'command' && <CommandCenterView onNavigated={navigate} />}

        {view === 'autonomous' && (
          <Suspense fallback={<div className="panel"><LoadingLine label="autonomous workspace" /></div>}>
            <AutonomousView />
          </Suspense>
        )}

        {view === 'falsification' && (
          /* Stitch Falsification Matrix → the dedicated matrix view over the
             real hypothesis-evaluation investigation (H1–H6 with engine
             verdicts, evidence links and the decision trace) */
          <Suspense fallback={<LoadingLine label="Loading falsification matrix…" />}>
            <FalsificationMatrixView
              key={params.toString()}
              presetParams={[...params.keys()].length > 0 ? params : undefined}
            />
          </Suspense>
        )}

        {view === 'investigate' && (
          <Suspense fallback={<LoadingLine label="Loading investigation workspace…" />}>
            <InvestigationView key={params.toString()} presetParams={presetParams} />
          </Suspense>
        )}

        {view === 'graph' && (
          <section className="panel">
            <h2>Engineering graph — provenance navigator</h2>
            <p className="muted small">
              Assembled on read from the investigation of the scope below.
              Click a node to trace its path; use the hypothesis focus to see
              supporting / contradicting / non-decisive evidence side by side.
            </p>
            <Suspense fallback={<LoadingLine label="Assembling engineering graph…" />}>
              <GraphPanel scopeParams={scopeParams} />
            </Suspense>
          </section>
        )}

        {view === 'replay' && (
          <section className="panel">
            <h2>Replay</h2>
            <p className="muted small">
              Deterministic replay: rebuild the snapshot, re-run the exact
              engine, compare canonical hashes. Divergence is reported as
              exact structured differences with categories.
            </p>
            <Suspense fallback={<LoadingLine label="Preparing deterministic replay…" />}>
              <ReplayPanel scopeParams={scopeParams} />
            </Suspense>
          </section>
        )}

        {view === 'compare' && (
          <section className="panel">
            <h2>Comparison</h2>
            <p className="muted small">
              Dimension-wise deltas between investigation A (current scope)
              and B (same scope, different lap). Neutral transition
              terminology — no better/worse, no winner.
            </p>
            <Suspense fallback={<LoadingLine label="Preparing comparison…" />}>
              <ComparePanel baseScope={scopeParams} />
            </Suspense>
          </section>
        )}

        {view === 'memory' && (
          <section className="panel">
            <h2>Engineering memory</h2>
            <p className="muted small">
              Evidence-bound, scope-limited memory derived on read and
              retrieved by exact scope — never semantic similarity, never
              universal truth.
            </p>
            <Suspense fallback={<LoadingLine label="Retrieving engineering memory…" />}>
              <MemoryPanel scopeParams={scopeParams} driverA={scopeParams().get('driver_a') || ''} />
            </Suspense>
          </section>
        )}

        {view === 'catalog' && (
          <Suspense fallback={<LoadingLine label="Loading data catalog…" />}>
            <CatalogExplorer
              presetSession={
                view === 'catalog' && [...params.keys()].length > 0
                  ? {
                      season: Number(params.get('season') || 0),
                      round: Number(params.get('round') || 0),
                      session_type: params.get('session_type') || 'RACE',
                    }
                  : undefined
              }
              onInvestigate={(session) =>
                navigate(
                  `investigate?season=${session.season}&round=${session.round}` +
                  `&session_type=${encodeURIComponent(session.session_type)}`,
                )
              }
            />
          </Suspense>
        )}

        {view === 'telemetry' && (
          <Suspense fallback={<LoadingLine label="Loading telemetry view…" />}>
            <TelemetryView />
          </Suspense>
        )}

        {view === 'attribution' && (
          <Suspense fallback={<LoadingLine label="Loading attribution view…" />}>
            <AttributionView />
          </Suspense>
        )}
        {view === 'fusion' && (
          <Suspense fallback={<LoadingLine label="Loading evidence fusion view…" />}>
            <EvidenceFusionView />
          </Suspense>
        )}
        {view === 'stint' && (
          <Suspense fallback={<LoadingLine label="Loading stint evidence view…" />}>
            <StintEvidenceView />
          </Suspense>
        )}
        {view === 'racegap' && (
          <Suspense fallback={<LoadingLine label="Loading race gap view…" />}>
            <RaceGapView />
          </Suspense>
        )}
        {view === 'counterfactual' && (
          <Suspense fallback={<LoadingLine label="Loading counterfactual view…" />}>
            <CounterfactualView
              key={params.toString()}
              presetParams={[...params.keys()].length > 0 ? params : undefined}
            />
          </Suspense>
        )}
        {view === 'envelope' && (
          <Suspense fallback={<LoadingLine label="Loading envelope view…" />}>
            <PerformanceEnvelopeView />
          </Suspense>
        )}
        {view === 'regime' && (
          <Suspense fallback={<LoadingLine label="Loading regimes view…" />}>
            <PerformanceRegimeView />
          </Suspense>
        )}
        {view === 'patterns' && (
          <Suspense fallback={<LoadingLine label="Loading patterns view…" />}>
            <PerformancePatternView />
          </Suspense>
        )}
        {view === 'patternevidence' && (
          <Suspense fallback={<LoadingLine label="Loading pattern evidence view…" />}>
            <PatternEvidenceView />
          </Suspense>
        )}
        </motion.div>
      </motion.main>

      {/* ================= STATUS BAR (§33 — only real state) ================= */}
      <motion.footer
        className="shell-statusbar"
        animate={{ opacity: zen ? 0 : 1 }}
        transition={T.micro}
        style={{ pointerEvents: zen ? 'none' : undefined }}
      >
        <span className="statusbar-item">
          <span
            className={`status-dot ${engineUp === false ? 'status-dot-down' : ''}`}
            aria-hidden="true"
          />
          {engineUp == null ? 'ENGINE PROBE…' : engineUp ? 'ENGINE REACHABLE · DETERMINISTIC CHAIN' : 'ENGINE UNREACHABLE — VIEWS DEGRADE HONESTLY'}
        </span>
        {engineUp !== false && <span className="statusbar-item">EVIDENCE-DRIVEN · ZERO STORAGE GROWTH</span>}
        {recentsCount > 0 && <span className="statusbar-item">{recentsCount} RECENT INVESTIGATION(S)</span>}
        <span className="statusbar-item" style={{ marginLeft: 'auto' }}>RACEWISE ENGINEERING WORKSTATION</span>
      </motion.footer>

      {/* ================= COMMAND PALETTE (§26) ================= */}
      {/* animated open, instant close — keyboard speed over spectacle (§34) */}
      {paletteOpen && (
          <motion.div
            className="overlay"
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
            initial={V.backdrop.initial}
            animate={V.backdrop.animate}
            transition={T.micro}
            onMouseDown={(e) => { if (e.target === e.currentTarget) setPaletteOpen(false) }}
          >
            <CommandPalette
              onClose={() => setPaletteOpen(false)}
              onNavigate={(v) => {
                setPaletteOpen(false)
                if (v === 'zen') { setZen((z) => !z); return }
                navigate(v)
              }}
              currentView={view}
              currentParams={params}
            />
          </motion.div>
      )}
    </div>
    </MotionConfig>
  )
}

