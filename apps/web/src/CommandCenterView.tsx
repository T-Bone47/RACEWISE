import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  IconSearch, IconGraph, IconHistory, IconGitCompare, IconDatabase, IconReload,
} from '@tabler/icons-react'
import {
  HYP_LABELS, QUESTION_INPUTS, QUESTION_TYPES, stateChipClass,
} from './types'
import type { QuestionScope, SearchResponse } from './types'
import { LoadingLine, StructuredError } from './workspace'

/* icon map for quick tiles — tabler (§44: one professional icon family) */
const QUICK_ICONS = {
  Data: IconDatabase,
  Graph: IconGraph,
  Memory: IconHistory,
  Compare: IconGitCompare,
  Search: IconSearch,
  Replay: IconReload,
} as const

/* ============ Phase 6Q — Command Center (default landing view) ============ */

export interface RecentInvestigation {
  investigation_id: string
  question_type: string
  scope: QuestionScope & { question_type?: string }
  output_hash: string
  conclusion_state: string
  evidence_count: number
  /* real per-hypothesis states + measured values saved from the run
     (rendered by the ledger; never synthesized) */
  hypothesis_states?: Record<string, string>
  observed_delta_s?: number | null
  residual_s?: number | null
  at: number
}

const RECENTS_KEY = 'racewise.recent.investigations.v1'

export function loadRecents(): RecentInvestigation[] {
  try {
    const raw = localStorage.getItem(RECENTS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as RecentInvestigation[]
    return Array.isArray(parsed) ? parsed.slice(0, 8) : []
  } catch {
    return []
  }
}

export function saveRecent(inv: RecentInvestigation) {
  try {
    const next = [inv, ...loadRecents().filter((r) => r.investigation_id !== inv.investigation_id)]
    localStorage.setItem(RECENTS_KEY, JSON.stringify(next.slice(0, 8)))
  } catch {
    /* storage unavailable — recents stay session-local */
  }
}

export function scopeParams(scope: QuestionScope & { question_type?: string }): URLSearchParams {
  const params = new URLSearchParams({
    driver_a: scope.driver_a,
    driver_b: scope.driver_b,
    season: String(scope.season),
    round: String(scope.round),
  })
  if (scope.question_type) params.set('question_type', scope.question_type)
  if (scope.lap_number != null) params.set('lap_number', String(scope.lap_number))
  if (scope.stint_number != null) params.set('stint_number', String(scope.stint_number))
  if (scope.pattern_id) params.set('pattern_id', scope.pattern_id)
  return params
}

const STEPS = ['QUESTION', 'SCOPE', 'HYPOTHESES', 'EVIDENCE PLAN', 'INVESTIGATE'] as const

/* Stitch "Fast Investigation Templates" mapped 1:1 onto the closed set of
   real question types (§26). Each pill prefills the launcher — nothing
   beyond the engine's own vocabulary is offered. */
interface Template { label: string; hint: string; question_type: string; session_type?: 'RACE' | 'QUALIFYING' }
const TEMPLATES: Template[] = [
  { label: 'Lap performance', hint: 'Δt decomposition for one lap', question_type: 'LAP_PERFORMANCE' },
  { label: 'Stint performance', hint: 'degradation trend over a stint', question_type: 'STINT_PERFORMANCE' },
  { label: 'Race gap', hint: 'official classification decomposition', question_type: 'RACE_GAP' },
  { label: 'Performance regimes', hint: 'deterministic slope segmentation', question_type: 'PERFORMANCE_REGIME' },
  { label: 'Cross-race pattern', hint: 'structural recurrence (needs pattern id)', question_type: 'CROSS_RACE_PATTERN' },
  { label: 'Hypothesis evaluation', hint: 'H1–H6 falsification protocol', question_type: 'HYPOTHESIS_EVALUATION' },
  { label: 'Counterfactual eligibility', hint: 'model-scope eligibility check', question_type: 'COUNTERFACTUAL_ELIGIBILITY' },
  { label: 'Qualifying lap (2018+)', hint: 'lap performance under QUALIFYING', question_type: 'LAP_PERFORMANCE', session_type: 'QUALIFYING' },
]

/* Phase 6T autonomous run record (subset rendered by the console) */
interface AutonomousRun {
  run_id?: string
  status?: string
  reason?: string
  question?: string
  stage_ledger?: Array<{ stage: string; status: string; detail?: string }>
  decision_trace?: Array<{ decision_id?: string; decision_type?: string; reason?: string }>
  tool_calls_consumed?: number
  engine_result_ref?: { status?: string; investigation_id?: string; output_hash?: string }
  budget?: Record<string, unknown>
}

interface CatalogSessionLite {
  season: number
  round: number
  race_name: string | null
}

export default function CommandCenterView({
  onNavigated,
}: {
  onNavigated?: (view: string) => void
}) {
  /* launcher state */
  const [questionType, setQuestionType] = useState<string>('LAP_PERFORMANCE')
  const [season, setSeason] = useState(2023)
  const [round, setRound] = useState(1)
  /* structured context is corrected on demand, not up front */
  const [contextOpen, setContextOpen] = useState(false)
  const [driverA, setDriverA] = useState('max-verstappen')
  const [driverB, setDriverB] = useState('sergio-perez')
  const [lapNumber, setLapNumber] = useState(6)
  const [stintNumber, setStintNumber] = useState(1)
  const [patternId, setPatternId] = useState('')
  const [hypothesisFilter, setHypothesisFilter] = useState<string[]>([])
  const [telemetrySessions, setTelemetrySessions] = useState<CatalogSessionLite[]>([])

  /* real system status */
  const [status, setStatus] = useState<{ sessions: number; db: string } | null>(null)
  const [statusError, setStatusError] = useState(false)
  const [recents] = useState<RecentInvestigation[]>(() => loadRecents())
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchQ, setSearchQ] = useState('')
  const [searchRes, setSearchRes] = useState<SearchResponse | null>(null)
  const [searchLoading, setSearchLoading] = useState(false)

  /* autonomous (6T) natural-language console state — real endpoint only */
  const [nlQuestion, setNlQuestion] = useState('')
  const [nlRunning, setNlRunning] = useState(false)
  const [nlRun, setNlRun] = useState<AutonomousRun | null>(null)
  const [nlError, setNlError] = useState<string | null>(null)

  /* focused trace preview: the selected recent investigation's real windows */
  const [focusRecent, setFocusRecent] = useState<RecentInvestigation | null>(null)
  const [focusWindows, setFocusWindows] = useState<Array<{ t_start_s: number; est_time_loss_s: number }> | null>(null)
  const [focusNote, setFocusNote] = useState<string | null>(null)

  const inputs = QUESTION_INPUTS[questionType] || []
  const step = useMemo(() => {
    if (!questionType) return 0
    if (!driverA.trim() || !driverB.trim() || driverA === driverB) return 1
    if (inputs.includes('lap_number') && !(lapNumber >= 1)) return 1
    if (inputs.includes('stint_number') && !(stintNumber >= 1)) return 1
    if (inputs.includes('pattern_id') && !patternId.trim()) return 1
    return 4
  }, [questionType, driverA, driverB, lapNumber, stintNumber, patternId, inputs])

  useEffect(() => {
    async function load() {
      try {
        const resp = await fetch('/api/catalog/sessions?capability=telemetry&page_size=100')
        if (!resp.ok) throw new Error(String(resp.status))
        const data = await resp.json()
        setTelemetrySessions((data.sessions || []).slice(0, 50))
        setStatus({ sessions: data.total ?? (data.sessions || []).length, db: 'canonical store' })
      } catch {
        setStatusError(true)
      }
    }
    load()
  }, [])

  const runSearch = useCallback(async (q: string) => {
    if (!q.trim()) {
      setSearchRes(null)
      return
    }
    setSearchLoading(true)
    try {
      const resp = await fetch(`/api/catalog/search?q=${encodeURIComponent(q.trim())}`)
      if (resp.ok) setSearchRes(await resp.json())
    } finally {
      setSearchLoading(false)
    }
  }, [])

  /* run the REAL Phase 6T autonomous investigation (question → evidence-bound
     answer); every failure mode is surfaced honestly */
  const runAutonomous = useCallback(async () => {
    const q = nlQuestion.trim()
    if (!q) return
    setNlRunning(true)
    setNlRun(null)
    setNlError(null)
    try {
      const resp = await fetch('/api/investigations/autonomous', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q }),
      })
      const body = await resp.json().catch(() => null)
      if (!resp.ok) {
        const detail = typeof body?.detail === 'string' ? body.detail
          : body?.detail ? JSON.stringify(body.detail) : `request failed (${resp.status})`
        setNlError(detail)
        return
      }
      setNlRun((body ?? {}) as AutonomousRun)
    } catch (e) {
      setNlError(e instanceof Error ? e.message : String(e))
    } finally {
      setNlRunning(false)
    }
  }, [nlQuestion])

  /* focused trace preview — real comparison windows for the selected recent */
  useEffect(() => {
    if (!focusRecent) return
    let cancelled = false
    setFocusWindows(null)
    setFocusNote(null)
    const p = new URLSearchParams({
      driver_a: focusRecent.scope.driver_a,
      driver_b: focusRecent.scope.driver_b,
    })
    if (focusRecent.scope.lap_number != null) p.set('lap', String(focusRecent.scope.lap_number))
    fetch(`/api/catalog/telemetry-comparison/${focusRecent.scope.season}/${focusRecent.scope.round}?${p}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((j: { verdict?: string; reason?: string; top_windows?: Array<{ t_start_s: number; est_time_loss_s: number }> }) => {
        if (cancelled) return
        if (j.verdict === 'PASS' && j.top_windows && j.top_windows.length > 0) {
          setFocusWindows(j.top_windows)
        } else {
          setFocusNote(j.verdict && j.verdict !== 'PASS'
            ? `${j.verdict}${j.reason ? ` — ${j.reason}` : ''}`
            : 'no comparison windows for this scope')
        }
      })
      .catch(() => { if (!cancelled) setFocusNote('UNAVAILABLE') })
    return () => { cancelled = true }
  }, [focusRecent])

  function scope(): QuestionScope & { question_type: string } {
    return {
      season,
      round,
      driver_a: driverA.trim(),
      driver_b: driverB.trim(),
      lap_number: inputs.includes('lap_number') ? lapNumber : null,
      stint_number: inputs.includes('stint_number') ? stintNumber : null,
      session_type: 'RACE',
      pattern_id: inputs.includes('pattern_id') && patternId.trim() ? patternId.trim() : null,
      question_type: questionType,
    }
  }

  function launch() {
    const s = scope()
    const params = scopeParams(s)
    params.set('question_type', questionType)
    if (hypothesisFilter.length > 0) params.set('hypotheses', hypothesisFilter.join(','))
    window.location.hash = `#/investigate?${params.toString()}`
    /* the App-level hashchange listener routes to the workspace with the full
       preset params; re-dispatch explicitly so an identical re-run (same hash
       string, no native event) still routes */
    window.dispatchEvent(new HashChangeEvent('hashchange'))
  }

  return (
    <div>
      {/* ---- THE QUESTION FIRST (mission: "What do you want to investigate?") ---- */}
      <section className="cmd-hero" aria-label="New investigation">
        {/* QUESTION-FIRST. The question is the product's entry point, so it is
            the only thing on screen at full weight. Structured context is
            resolved automatically and revealed only when the operator needs to
            correct it — progressive disclosure, not a form. */}
        <p className="cmd-eyebrow">New investigation</p>
        <h1 className="cmd-headline">What are you investigating?</h1>

        <div className="cmd-ask">
          <textarea
            className="cmd-ask-input"
            rows={2}
            value={nlQuestion}
            placeholder="Why did Verstappen lose time to Pérez in sector 2 at Bahrain 2023?"
            onChange={(e) => setNlQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey || !e.shiftKey)) {
                e.preventDefault()
                void runAutonomous()
              }
            }}
            aria-label="Engineering question"
          />
          <button
            className="rw-btn rw-btn--primary rw-btn--lg cmd-ask-go"
            onClick={() => void runAutonomous()}
            disabled={nlRunning || !nlQuestion.trim()}
          >
            {nlRunning ? 'Investigating…' : 'Investigate'}
          </button>
        </div>

        <p className="cmd-ask-hint">
          Runs the full chain — question → context → evidence → falsification →
          synthesis. The deterministic engine decides what the answer is.
        </p>
        {nlError && (
          <div className="catalog-error" role="alert">{nlError}</div>
        )}
        {nlRun && (
          <div className="nl-result" aria-label="Autonomous run result">
            <div className="nl-result-head">
              <span className="ef-badge st-supported">{nlRun.status}</span>
              {nlRun.reason && <span className="muted small">{nlRun.reason}</span>}
              {nlRun.run_id && <span className="mono small">run {nlRun.run_id}</span>}
              {nlRun.engine_result_ref?.investigation_id && (
                <span className="mono small" title="deterministic engine investigation id">
                  engine {nlRun.engine_result_ref.investigation_id}
                </span>
              )}
            </div>
            {nlRun.stage_ledger && nlRun.stage_ledger.length > 0 && (
              <ol className="nl-stages">
                {nlRun.stage_ledger.map((s, i) => (
                  <li key={`${s.stage}-${i}`} className="nl-stage">
                    <span className="mono small">{String(i + 1).padStart(2, '0')} {s.stage}</span>
                    <span className="muted small">{s.status}{s.detail ? ` — ${s.detail}` : ''}</span>
                  </li>
                ))}
              </ol>
            )}
            <p className="muted small">
              {nlRun.tool_calls_consumed !== undefined ? `${nlRun.tool_calls_consumed} tool calls · ` : ''}
              full run record and replay in the <button className="linklike" onClick={() => onNavigated?.('autonomous')}>Autonomous Query view</button>.
            </p>
          </div>
        )}

        {/* fast investigation templates — real question types only */}
        <div className="rw-disclosure" style={{ borderTop: 'none', marginTop: 'var(--rw-s5)', paddingTop: 0 }}>
          <span className="rw-k" style={{ marginBottom: 0 }}>Or start from a known question type</span>
          <div className="cmd-templates">
            {TEMPLATES.map((t) => (
              <button
                key={t.label}
                className="cmd-template"
                title={t.hint}
                onClick={() => {
                  setQuestionType(t.question_type)
                  if (t.session_type === 'QUALIFYING' && t.question_type === 'STINT_PERFORMANCE') {
                    setQuestionType('LAP_PERFORMANCE')
                  }
                }}
              >
                <b>{t.label}</b>
                <span>{t.hint}</span>
              </button>
            ))}
          </div>
        </div>

        {/* ---- structured scope (the deterministic launcher) ---- */}
        <div className="launcher-steps" aria-hidden="true" hidden={!contextOpen}>
          {STEPS.map((s, i) => (
            <span key={s} className={`step ${i < step ? 'done' : i === step ? 'active' : ''}`}>
              {i + 1}. {s}
            </span>
          ))}
        </div>

        <div className="rw-disclosure">
          <button
            type="button"
            className="rw-btn rw-btn--ghost rw-btn--sm"
            aria-expanded={contextOpen}
            onClick={() => setContextOpen((o) => !o)}
          >
            {contextOpen ? '▾' : '▸'} Edit context
          </button>

          {/* resolved context — what the engine is actually scoped to right now.
              Read-only by default; the operator sees the truth before editing it. */}
          {!contextOpen && (
            <div className="rw-resolved" aria-label="Resolved context">
              <span className="rw-k">Resolved context</span>
              <div className="rw-resolved-chips">
                <span className="rw-chip rw-chip--observed">{season} · R{round}</span>
                <span className="rw-chip rw-chip--observed">{questionType.replace(/_/g, ' ').toLowerCase()}</span>
                <span className="rw-chip rw-chip--observed">{driverA} ↔ {driverB}</span>
                {inputs.includes('lap_number') && (
                  <span className="rw-chip rw-chip--observed">lap {lapNumber}</span>
                )}
                {inputs.includes('stint_number') && (
                  <span className="rw-chip rw-chip--observed">stint {stintNumber}</span>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="controls rw-context-fields" hidden={!contextOpen}>
          <label>
            question type:{' '}
            <select value={questionType} onChange={(e) => setQuestionType(e.target.value)}>
              {QUESTION_TYPES.map((q) => <option key={q} value={q}>{q}</option>)}
            </select>
          </label>
          <label>
            season:{' '}
            <select value={season} onChange={(e) => setSeason(Number(e.target.value))}>
              {Array.from(new Set([...telemetrySessions.map((s) => s.season), season]))
                .sort((a, b) => b - a).map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </label>
          <label>
            round:{' '}
            <input type="number" min={1} max={99} value={round} style={{ width: 64 }}
                   onChange={(e) => setRound(Number(e.target.value))} />
          </label>
          <label>
            driver A:{' '}
            <input type="text" value={driverA} style={{ width: 150 }}
                   onChange={(e) => setDriverA(e.target.value)} />
          </label>
          <label>
            driver B:{' '}
            <input type="text" value={driverB} style={{ width: 150 }}
                   onChange={(e) => setDriverB(e.target.value)} />
          </label>
          {inputs.includes('lap_number') && (
            <label>
              lap:{' '}
              <input type="number" min={1} value={lapNumber} style={{ width: 64 }}
                     onChange={(e) => setLapNumber(Number(e.target.value))} />
            </label>
          )}
          {inputs.includes('stint_number') && (
            <label>
              stint:{' '}
              <input type="number" min={1} value={stintNumber} style={{ width: 64 }}
                     onChange={(e) => setStintNumber(Number(e.target.value))} />
            </label>
          )}
          {inputs.includes('pattern_id') && (
            <label>
              pattern id:{' '}
              <input type="text" value={patternId} style={{ minWidth: 220 }}
                     placeholder="pattern id from Cross-Race Patterns"
                     onChange={(e) => setPatternId(e.target.value)} />
            </label>
          )}
        </div>

        <div className="controls" hidden={!contextOpen}>
          <span className="muted small">hypothesis subset (optional, never ranked):</span>
          {Object.entries(HYP_LABELS).map(([id, label]) => (
            <label key={id} style={{ gap: 3 }}>
              <input
                type="checkbox"
                checked={hypothesisFilter.includes(id)}
                onChange={(e) => setHypothesisFilter((cur) =>
                  e.target.checked ? [...cur, id] : cur.filter((h) => h !== id))}
              />
              {label}
            </label>
          ))}
        </div>

        <div className="muted small" style={{ marginBottom: 10 }}>
          evidence plan will execute: {(questionType && QUESTION_INPUTS[questionType] !== undefined) ? 'per the closed evidence plan' : '—'} ·
          {' '}drivers must be distinct · scope data is checked at run time (UNAVAILABLE is reported, never broadened)
        </div>

        <button className="rw-btn rw-btn--secondary" onClick={launch} disabled={step < 4}>
          {step < 4 ? 'Complete steps 1–4' : 'Open structured investigation →'}
        </button>
      </section>

      {/* ---- RECENT INVESTIGATIONS (real, or explicit empty state) ---- */}
      <section className="panel" aria-label="Recent investigations">
        <h2>Investigations ledger</h2>
        {recents.length === 0 ? (
          <div className="empty-state">
            No investigation has been run in this browser yet. Completed
            investigations appear here with their scope and conclusion state —
            nothing is listed until you actually run one.
          </div>
        ) : (
          <div className="recent-list">
            {recents.map((r) => (
              <button
                key={r.investigation_id}
                className={`recent-item ${focusRecent?.investigation_id === r.investigation_id ? 'selected' : ''}`}
                onClick={() => {
                  setFocusRecent((cur) =>
                    cur?.investigation_id === r.investigation_id ? null : r)
                }}
                onDoubleClick={() => {
                  const params = scopeParams(r.scope)
                  params.set('question_type', r.question_type)
                  window.location.hash = `#/investigate?${params.toString()}`
                  window.dispatchEvent(new HashChangeEvent('hashchange'))
                  onNavigated?.('investigate')
                }}
                title="Click: focus (trace preview). Double-click: open the workspace."
              >
                <span className={`ef-badge ${r.conclusion_state === 'SUPPORTED_BY_AVAILABLE_EVIDENCE' ? 'st-supported' : r.conclusion_state === 'MIXED_EVIDENCE' ? 'st-mixed' : 'st-untestable'}`}>
                  {r.conclusion_state.replace(/_/g, ' ')}
                </span>
                <span>{r.question_type}</span>
                <span className="muted small">
                  {r.scope.season} R{r.scope.round} · {r.scope.driver_a} vs {r.scope.driver_b}
                  {r.scope.lap_number != null ? ` · lap ${r.scope.lap_number}` : ''}
                  {r.scope.stint_number != null ? ` · stint ${r.scope.stint_number}` : ''}
                </span>
                {r.observed_delta_s != null && (
                  <span className="mono small" title="measured observed delta from the run">
                    Δ {r.observed_delta_s} s
                  </span>
                )}
                {r.residual_s != null && (
                  <span className="mono small" title="unassigned residual (UNRESOLVED)">
                    residual {r.residual_s} s
                  </span>
                )}
                {r.hypothesis_states && (
                  <span className="recent-hyps" title="real per-hypothesis states from the run">
                    {Object.entries(r.hypothesis_states).map(([id, st]) => (
                      <span key={id} className={`hyp-dot ${stateChipClass(st)}`} title={`${id}: ${st}`}>
                        {id.split('_')[0]}
                      </span>
                    ))}
                  </span>
                )}
                <span className="muted small mono" style={{ marginLeft: 'auto' }}>
                  {r.investigation_id.slice(0, 10)} · {r.evidence_count} evidence items
                </span>
              </button>
            ))}
          </div>
        )}
        {/* ---- FOCUSED TRACE PREVIEW (real windows for the selected run) ---- */}
        {focusRecent && (
          <div className="focus-preview" aria-label="Focused trace preview">
            <div className="focus-preview-head">
              <span className="t-microlabel">
                Focused trace preview — {focusRecent.investigation_id.slice(0, 10)} ·{' '}
                {focusRecent.scope.driver_a} vs {focusRecent.scope.driver_b}
                {focusRecent.scope.lap_number != null ? ` · lap ${focusRecent.scope.lap_number}` : ''}
              </span>
              <button
                className="linklike small"
                onClick={() => {
                  const params = scopeParams(focusRecent.scope)
                  params.set('question_type', focusRecent.question_type)
                  window.location.hash = `#/investigate?${params.toString()}`
                  window.dispatchEvent(new HashChangeEvent('hashchange'))
                  onNavigated?.('investigate')
                }}
              >
                open workspace →
              </button>
            </div>
            {focusWindows && focusWindows.length > 0 ? (
              <div className="focus-bars" role="img"
                aria-label={`${focusWindows.length} comparison windows, largest estimated loss highlighted`}>
                {(() => {
                  const maxLoss = Math.max(...focusWindows.map((w) => Math.abs(w.est_time_loss_s)))
                  return focusWindows.map((w) => (
                    <div
                      key={w.t_start_s}
                      className="focus-bar"
                      style={{ height: `${Math.max((Math.abs(w.est_time_loss_s) / maxLoss) * 100, 3)}%` }}
                      title={`window t=${w.t_start_s}s · est loss ${w.est_time_loss_s}s`}
                    />
                  ))
                })()}
              </div>
            ) : (
              <div className="empty-state">{focusNote || 'no comparison windows for this scope'}</div>
            )}
            <p className="muted small">
              Per-window estimated time loss from the deterministic comparison engine for
              this scope — the same evidence class the investigation evaluated.
            </p>
          </div>
        )}
      </section>

      {/* ---- SHORTCUTS ---- */}
      <section className="panel" aria-label="Shortcuts">
        <h2>Evidence / Graph / Memory shortcuts</h2>
        <div className="quick-grid">
          {[['Data', 'catalog'], ['Graph', 'graph'], ['Memory', 'memory'],
            ['Compare', 'compare'], ['Search', 'search'], ['Replay', 'replay']].map(([label, view]) => {
            const Icon = QUICK_ICONS[label as keyof typeof QUICK_ICONS]
            return (
              <button
                key={label}
                className="quick-tile"
                onClick={() => {
                  if (view === 'search') { setSearchOpen(true); onNavigated?.('') }
                  else onNavigated?.(view)
                }}
              >
                <span className="q-label">
                  <Icon size={15} strokeWidth={1.75} aria-hidden="true" /> {label}
                </span>
                {{
                  Data: 'Browse the canonical catalog and launch from a session',
                  Graph: 'Open the engineering graph for the current scope',
                  Memory: 'Exact-scope engineering memory (derived on read)',
                  Compare: 'Dimension-wise comparison of two investigations',
                  Search: 'Find races, drivers and hypotheses (Ctrl/Cmd + K)',
                  Replay: 'Deterministic replay of an investigation',
                }[label]}
              </button>
            )
          })}
        </div>
      </section>

      {/* ---- SYSTEM STATUS (only real, catalog-derived state) ---- */}
      <section className="panel" aria-label="System status">
        <h2>System status</h2>
        {statusError ? (
          <StructuredError code="DATA_UNAVAILABLE"
            message="The canonical catalog API did not answer. No status is shown rather than a fabricated one."
            hint="Start the API server and reload." />
        ) : !status ? (
          <LoadingLine label="Reading canonical catalog…" />
        ) : (
          <div className="muted small">
            <span className="status-dot" aria-hidden="true" /> DATA AVAILABLE —{' '}
            {status.sessions} catalog sessions with telemetry capability ·{' '}
            investigations READY · deterministic analytical chain READY ·{' '}
            graph READY (derived on read)
          </div>
        )}
      </section>

      {/* ---- SEARCH OVERLAY (reuses the palette styles) ---- */}
      {searchOpen && (
        <div className="overlay" role="dialog" aria-modal="true" aria-label="Engineering search"
             onMouseDown={(e) => { if (e.target === e.currentTarget) setSearchOpen(false) }}>
          <div className="palette">
            <input
              autoFocus
              value={searchQ}
              placeholder="Search races (e.g. “2023 1”), drivers, hypotheses, ids…"
              onChange={(e) => { setSearchQ(e.target.value); runSearch(e.target.value) }}
              onKeyDown={(e) => { if (e.key === 'Escape') setSearchOpen(false) }}
            />
            <div className="palette-list">
              {searchLoading && <div className="palette-empty">Searching…</div>}
              {!searchLoading && searchRes && searchRes.result_count === 0 && (
                <div className="palette-empty">
                  No typed result for “{searchQ}”. Search is exact/structured —
                  try a driver slug (“max-verstappen”), season+round (“2023 1”),
                  a hypothesis (“corner”), or a 16-hex id.
                </div>
              )}
              {!searchLoading && searchRes?.results.map((r, i) => (
                <button
                  key={`${r.result_type}-${i}`}
                  className="palette-item"
                  onClick={() => {
                    setSearchOpen(false)
                    const ref = r.ref
                    if (ref.season != null && ref.round != null) {
                      window.location.hash = `#/catalog`
                      window.dispatchEvent(new HashChangeEvent('hashchange'))
                    } else if (r.result_type === 'HYPOTHESIS') {
                      window.location.hash = `#/investigate?question_type=LAP_PERFORMANCE&driver_a=max-verstappen&driver_b=sergio-perez&season=2023&round=1&lap_number=6`
                      window.dispatchEvent(new HashChangeEvent('hashchange'))
                    } else {
                      window.location.hash = `#/investigate`
                      window.dispatchEvent(new HashChangeEvent('hashchange'))
                    }
                    onNavigated?.('')
                  }}
                >
                  <span className="p-type">{r.result_type}</span>
                  <span>{r.label}</span>
                  <span className="muted small">{r.detail.slice(0, 60)}</span>
                </button>
              ))}
            </div>
            <div className="palette-hint">
              <span><kbd>Esc</kbd> close</span>
              <span>exact/structured matching only — no semantic search</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
