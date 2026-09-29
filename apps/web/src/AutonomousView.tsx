import { useEffect, useRef, useState } from 'react'
import { stateChipClass } from './types'

/* ============ Phase 6T: autonomous investigation workspace ============ */

interface StageEntry { stage: string; status: string; detail?: string | null }
interface DecisionEntry {
  decision_id: string; order: number; decision_type: string
  reason: string; selected_action: string; tool?: string | null
  evidence_refs?: string[]
}
interface AutonomousRun {
  run_id: string
  status: string
  reason?: string | null
  failed_stage?: string | null
  question_text?: string | null
  question?: { text?: string; question_type?: string; scope?: Record<string, unknown>; question_object_hash?: string }
  context?: Record<string, unknown>
  stage_ledger?: StageEntry[]
  decision_trace?: DecisionEntry[]
  hypothesis_states?: Record<string, string>
  evidence_conflicts?: Array<Record<string, unknown>>
  data_availability?: Record<string, { requirement: string; availability: string }>
  evidence_plan?: Array<{ phase: string; tool: string; purpose: string; why_planned: string }>
  hypothesis_selection?: { selected: string[]; why_selected: string; why_not_selected: Record<string, string>; policy: string }
  engine_result_ref?: { investigation_id?: string; output_hash?: string; status?: string; evidence_items?: number; layers_executed?: string[] }
  synthesis?: { conclusion_state?: string; established_facts?: Array<Record<string, unknown>> } | null
  memory?: { items_derived?: number; related?: { match_count?: number; policy?: string; neighbor_runs?: Array<{ season: number; status: string }> } }
  budget?: { limits?: Record<string, number>; consumed?: Record<string, number>; remaining?: Record<string, number> }
  metrics?: { total_runtime_ms?: number; engine_runtime_ms?: number; tool_calls?: number }
  injection_scan?: { flagged?: boolean; patterns?: string[]; policy?: string }
  clarification?: { missing?: string[]; candidates?: string[]; reason?: string } | null
  provenance?: Record<string, unknown>
}

const STAGES = [
  'CREATED', 'QUESTION_PARSED', 'CONTEXT_RESOLVED', 'DATA_CHECKED',
  'HYPOTHESES_SELECTED', 'EVIDENCE_PLANNED', 'EVIDENCE_COLLECTING',
  'HYPOTHESES_EVALUATED', 'FALSIFICATION', 'COUNTERFACTUAL_CHECK',
  'SYNTHESIS', 'VERIFICATION', 'COMPLETED',
]

function StageTimeline({ ledger }: { ledger: StageEntry[] }) {
  const completed = new Set(
    ledger.filter((s) => s.status === 'COMPLETED').map((s) => s.stage))
  const inProgress = ledger.filter((s) => s.status === 'IN_PROGRESS').map((s) => s.stage)
  const active = inProgress.length ? inProgress[inProgress.length - 1] : null
  return (
    <div className="auto-timeline" aria-label="investigation lifecycle">
      {STAGES.map((s) => {
        const done = completed.has(s)
        const isActive = active === s && !done
        return (
          <div key={s} className={`auto-stage ${done ? 'done' : ''} ${isActive ? 'active' : ''}`}>
            <span className="auto-stage-mark" aria-hidden="true">{done ? '✓' : isActive ? '●' : '○'}</span>
            <span className="auto-stage-label">{s.replace(/_/g, ' ').toLowerCase()}</span>
          </div>
        )
      })}
    </div>
  )
}

export default function AutonomousView() {
  const [question, setQuestion] = useState('')
  const [season, setSeason] = useState('')
  const [round, setRound] = useState('')
  const [sessionType, setSessionType] = useState('RACE')
  const [driverA, setDriverA] = useState('')
  const [driverB, setDriverB] = useState('')

  const [runId, setRunId] = useState<string | null>(null)
  const [run, setRun] = useState<AutonomousRun | null>(null)
  const [liveStages, setLiveStages] = useState<StageEntry[]>([])
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<{ status: number; detail: Record<string, unknown> } | null>(null)
  const [replayVerdict, setReplayVerdict] = useState<string | null>(null)
  const [openDecision, setOpenDecision] = useState<string | null>(null)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => () => esRef.current?.close(), [])

  async function start() {
    setError(null); setReplayVerdict(null); setRun(null); setLiveStages([]); setRunId(null)
    const context: Record<string, unknown> = {}
    if (season.trim()) context.season = Number(season)
    if (round.trim()) context.round = Number(round)
    if (sessionType) context.session_type = sessionType
    if (driverA.trim()) context.driver_a = driverA.trim()
    if (driverB.trim()) context.driver_b = driverB.trim()
    try {
      const resp = await fetch('/api/investigations/autonomous', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, context }),
      })
      if (!resp.ok) {
        const detail = (await resp.json().catch(() => ({}))) as { detail?: Record<string, unknown> }
        setError({ status: resp.status, detail: (detail.detail as Record<string, unknown>) || detail })
        return
      }
      const data = (await resp.json()) as AutonomousRun
      setRun(data)
      setRunId(data.run_id)
      streamRun(data.run_id)
    } catch (e) {
      setError({ status: 0, detail: { reason: String(e) } })
    }
  }

  /* real stage progression via SSE — the endpoint re-executes the run
     with a stage callback and emits each lifecycle transition as it
     happens (no simulated progress) */
  function streamRun(id: string) {
    esRef.current?.close()
    setStreaming(true)
    const es = new EventSource(`/api/investigations/autonomous/${id}/stream`)
    esRef.current = es
    es.onmessage = (ev) => {
      try {
        const payload = JSON.parse(ev.data) as { type: string; stage?: string; status?: string; detail?: string; record?: AutonomousRun }
        if (payload.type === 'stage' && payload.stage) {
          const stageName: string = payload.stage
          const stageStatus: string = payload.status || ''
          const stageDetail: string | undefined =
            typeof payload.detail === 'string' ? payload.detail : undefined
          setLiveStages((prev) => {
            const filtered = prev.filter(
              (s) => !(s.stage === stageName && s.status === 'IN_PROGRESS' && stageStatus === 'COMPLETED'))
            return [...filtered, { stage: stageName, status: stageStatus, detail: stageDetail }]
          })
        } else if (payload.type === 'run.completed' && payload.record) {
          setRun(payload.record)
          setStreaming(false)
          es.close()
        } else if (payload.type === 'run.failed') {
          setStreaming(false)
          es.close()
        } else if (payload.type === 'done') {
          setStreaming(false)
          es.close()
        }
      } catch { /* malformed event: ignore, the POST result remains authoritative */ }
    }
    es.onerror = () => { setStreaming(false); es.close() }
  }

  async function replay() {
    if (!runId) return
    setReplayVerdict(null)
    const resp = await fetch(`/api/investigations/autonomous/${runId}/replay`, { method: 'POST' })
    if (resp.ok) {
      const data = (await resp.json()) as { status: string }
      setReplayVerdict(data.status)
    } else {
      setReplayVerdict('REPLAY_FAILED')
    }
  }

  function openGraph() {
    const scope = (run?.question?.scope || {}) as Record<string, unknown>
    const params = new URLSearchParams()
    if (scope.season) params.set('season', String(scope.season))
    if (scope.round) params.set('round', String(scope.round))
    if (scope.session_type) params.set('session_type', String(scope.session_type))
    if (scope.driver_a) params.set('driver_a', String(scope.driver_a))
    if (scope.driver_b) params.set('driver_b', String(scope.driver_b))
    if (scope.lap_number) params.set('lap_number', String(scope.lap_number))
    if (scope.stint_number) params.set('stint_number', String(scope.stint_number))
    if (scope.pattern_id) params.set('pattern_id', String(scope.pattern_id))
    /* the 6S graph contract deterministically reconstructs the canonical
       input: question_type is part of that identity */
    const questionType = (run?.question as { question_type?: string } | undefined)?.question_type
      || (scope.question_type as string | undefined)
    if (questionType) params.set('question_type', String(questionType))
    /* address the exact investigation when the run has one (Phase 6S
       investigation-id addressing): scope-only graphs may not resolve */
    if (engineId) params.set('investigation_id', engineId)
    window.location.hash = `#/graph?${params.toString()}`
    window.dispatchEvent(new HashChangeEvent('hashchange'))
  }

  const failureState = run && run.status !== 'COMPLETED' ? run.status : null
  const engineId = run?.engine_result_ref?.investigation_id
  const related = run?.memory?.related

  return (
    <section className="panel auto-panel">
      <h2>Autonomous investigation</h2>
      <p className="muted small">
        Ask a natural-language engineering question. The orchestrator
        autonomously plans and collects evidence through the deterministic
        engine — the engine stays the sole authority for data, hypothesis
        states and provenance; orchestration decisions are traced and
        separated from engine results below.
      </p>

      {/* ============ QUESTION INPUT ============ */}
      <div className="auto-question">
        <label htmlFor="auto-q">What do you want to investigate?</label>
        <textarea
          id="auto-q"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={'e.g. Why did Verstappen lose time to Perez on lap 6 in Bahrain 2023?'}
          rows={2}
        />
        <div className="controls">
          <label>season: <input type="number" min={1950} max={2027} value={season} style={{ width: 80 }}
            onChange={(e) => setSeason(e.target.value)} placeholder="auto" /></label>
          <label>round: <input type="number" min={1} max={99} value={round} style={{ width: 60 }}
            onChange={(e) => setRound(e.target.value)} placeholder="auto" /></label>
          <label>session:
            <select value={sessionType} onChange={(e) => setSessionType(e.target.value)}>
              <option value="RACE">Race</option>
              <option value="QUALIFYING">Qualifying (2018+)</option>
            </select>
          </label>
          <label>driver A: <input type="text" value={driverA} style={{ width: 140 }}
            onChange={(e) => setDriverA(e.target.value)} placeholder="auto" /></label>
          <label>driver B: <input type="text" value={driverB} style={{ width: 140 }}
            onChange={(e) => setDriverB(e.target.value)} placeholder="auto" /></label>
          <button className="primary" onClick={start} disabled={!question.trim() || streaming}>
            {streaming ? 'Investigating…' : 'Start investigation'}
          </button>
        </div>
        <p className="muted small">
          Optional context: anything left blank must be resolvable from the
          question text — the orchestrator asks instead of guessing.
        </p>
      </div>

      {/* ============ ERROR / CLARIFICATION ============ */}
      {error && (
        <div className="auto-failure" role="alert">
          <strong>HTTP {error.status}</strong>
          <span> {String((error.detail as { status?: string }).status || '')}</span>
          <p>{String((error.detail as { reason?: string }).reason || 'request failed')}</p>
          {Array.isArray((error.detail as { supported_question_types?: string[] }).supported_question_types) && (
            <p className="muted small">
              supported: {((error.detail as { supported_question_types?: string[] }).supported_question_types || []).join(', ')}
            </p>
          )}
        </div>
      )}
      {run?.clarification && (
        <div className="auto-failure" role="alert">
          <strong>CONTEXT_UNRESOLVED</strong>
          <p>{run.clarification.reason}</p>
          {run.clarification.missing && <p>missing: {run.clarification.missing.join(', ')}</p>}
          {run.clarification.candidates && <p>candidates: {run.clarification.candidates.join(', ')}</p>}
        </div>
      )}

      {/* ============ LIVE STAGE TIMELINE ============ */}
      {(liveStages.length > 0 || run) && (
        <div className="auto-stages">
          <h3>Investigation plan</h3>
          <StageTimeline ledger={run?.stage_ledger && run.stage_ledger.length ? run.stage_ledger : liveStages} />
        </div>
      )}

      {run && (
        <>
          {/* ============ RUN HEADER ============ */}
          <div className="inv-title">
            <span className="qid mono">{run.run_id}</span>
            <span className={`ef-badge ${failureState ? 'st-contradicted' : 'st-supported'}`}>
              {failureState || 'COMPLETED'}
            </span>
            {failureState && <span className="muted small">failed at {run.failed_stage}</span>}
            {failureState && <span className="muted">{run.reason}</span>}
            {run.injection_scan?.flagged && (
              <span className="ef-badge st-mixed" title={run.injection_scan.policy}>
                ⚠ instruction-like text quarantined ({run.injection_scan.patterns?.join(', ')})
              </span>
            )}
            <span className="spacer" />
            <button onClick={replay}>Replay</button>
            {engineId && <button onClick={openGraph}>Open graph →</button>}
          </div>
          {replayVerdict && (
            <p className="small">
              replay: <strong>{replayVerdict}</strong>
              {replayVerdict === 'IDENTICAL' ? ' — deterministic surfaces reproduced exactly' : ''}
            </p>
          )}
          {run.question?.question_object_hash && (
            <p className="muted small mono">question object {run.question.question_object_hash}</p>
          )}

          {/* ============ DATA AVAILABILITY + HYPOTHESIS SELECTION (orchestration) ============ */}
          {run.data_availability && (
            <div className="auto-orchestration">
              <h3>Data availability <span className="muted small">(orchestrator, from the canonical catalog)</span></h3>
              <div className="auto-facets">
                {Object.entries(run.data_availability).map(([facet, v]) => (
                  <span key={facet} className={`ef-badge ${v.availability === 'AVAILABLE' ? 'st-supported' : v.availability === 'PARTIAL' ? 'st-mixed' : 'st-insufficient'}`}>
                    {facet}: {v.availability} <span className="muted">({v.requirement})</span>
                  </span>
                ))}
              </div>
            </div>
          )}
          {run.hypothesis_selection && (
            <div className="auto-orchestration">
              <h3>Hypothesis selection <span className="muted small">(orchestrator narrows scope; the engine decides all states)</span></h3>
              <p className="small">{run.hypothesis_selection.why_selected}</p>
              <div className="auto-facets">
                {run.hypothesis_selection.selected.map((h) => <span key={h} className="ef-badge st-observed">{h}</span>)}
              </div>
              {Object.keys(run.hypothesis_selection.why_not_selected || {}).length > 0 && (
                <p className="muted small">
                  not selected: {Object.entries(run.hypothesis_selection.why_not_selected).map(([h, w]) => `${h} (${w})`).join('; ')}
                </p>
              )}
            </div>
          )}
          {run.evidence_plan && (
            <div className="auto-orchestration">
              <h3>Evidence plan</h3>
              <table className="tbl">
                <thead><tr><th>phase</th><th>tool</th><th>purpose</th></tr></thead>
                <tbody>
                  {run.evidence_plan.map((s, i) => (
                    <tr key={i}><td>{s.phase}</td><td className="mono">{s.tool}</td><td>{s.purpose}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* ============ HYPOTHESIS PANEL (engine states) ============ */}
          {run.hypothesis_states && (
            <div className="auto-hypotheses">
              <h3>Hypotheses <span className="muted small">(deterministic engine states)</span></h3>
              <div className="auto-facets">
                {Object.entries(run.hypothesis_states).map(([h, state]) => (
                  <span key={h} className={`ef-badge ${stateChipClass(state)}`} title={h}>
                    {h.replace(/_/g, ' ')}: <strong>{state}</strong>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* ============ CONTRADICTIONS ============ */}
          {run.evidence_conflicts && run.evidence_conflicts.length > 0 && (
            <div className="auto-contradictions">
              <h3>Contradictions <span className="muted small">(preserved, never resolved away)</span></h3>
              {run.evidence_conflicts.map((c, i) => (
                <p key={i} className="small">
                  <span className={`ef-badge ${stateChipClass('CONTRADICTED')}`}>{String(c.conflict_type || 'CONFLICT')}</span>{' '}
                  {String(c.description || '')}
                </p>
              ))}
            </div>
          )}

          {/* ============ DECISION TRACE ============ */}
          {run.decision_trace && run.decision_trace.length > 0 && (
            <div className="auto-trace">
              <h3>Decision trace <span className="muted small">(every autonomous decision, auditable)</span></h3>
              <table className="tbl">
                <thead><tr><th>#</th><th>decision</th><th>reason (orchestrator)</th><th>action</th><th>tool</th></tr></thead>
                <tbody>
                  {run.decision_trace.map((d) => (
                    <tr key={d.decision_id} onClick={() => setOpenDecision(openDecision === d.decision_id ? null : d.decision_id)}
                      style={{ cursor: 'pointer' }}>
                      <td className="mono">{d.decision_id}</td>
                      <td><span className="ef-badge st-observed">{d.decision_type}</span></td>
                      <td>{d.reason.replace(/^ORCHESTRATOR: /, '')}</td>
                      <td className="small">{d.selected_action}</td>
                      <td className="mono small">{d.tool || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* ============ ENGINE RESULT ============ */}
          {engineId ? (
            <div className="auto-engine">
              <h3>Deterministic engine result <span className="muted small">(the authority)</span></h3>
              <p className="small">
                investigation <span className="mono">{engineId}</span>{' '}
                <StateChipInline state={run.engine_result_ref?.status} />{' '}
                — {run.engine_result_ref?.evidence_items} evidence items from layers{' '}
                {(run.engine_result_ref?.layers_executed || []).join(', ')}
              </p>
              <p className="muted small">
                full evidence ledger, synthesis and provenance are served by the existing
                engineering-investigation contract under this id.
              </p>
            </div>
          ) : (
            run && failureState && (
              <p className="muted small">
                No engine result: the run stopped honestly at {run.failed_stage}.
              </p>
            )
          )}

          {/* ============ MEMORY ============ */}
          {run.memory && (
            <div className="auto-memory">
              <h3>Memory <span className="muted small">(derived via the unchanged Phase 6O rules)</span></h3>
              <p className="small">
                {run.memory.items_derived} item(s) derived from this investigation
                {related ? `; ${related.match_count} structurally related item(s) from ±1-season neighbors` : ''}.
              </p>
              {related && (
                <p className="muted small">{related.policy}</p>
              )}
            </div>
          )}

          {/* ============ BUDGET + METRICS ============ */}
          {run.budget && (
            <p className="muted small">
              budget: {run.budget.consumed?.tool_calls}/{run.budget.limits?.max_tool_calls} tool calls ·
              engine {run.metrics?.engine_runtime_ms ?? '—'} ms · total {run.metrics?.total_runtime_ms ?? '—'} ms
            </p>
          )}
        </>
      )}
    </section>
  )
}

function StateChipInline({ state }: { state?: string | null }) {
  if (!state) return null
  return <span className={`ef-badge ${stateChipClass(state)}`}>{state}</span>
}
