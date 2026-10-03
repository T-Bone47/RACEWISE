import { useCallback, useState } from 'react'

/* ============ Universal engineering question (question engine) ============
   The universal entry point. One free-text question in; the structured answer
   the question engine produced out. No question-type selector is involved at
   all — the engine discovers capabilities from its registry.

   What this panel refuses to do, because the engine would not:
   - it never renders a confidence percentage
   - it never renames an engine hypothesis state
   - it never shows a counterfactual without its MODELLED label
   - it never hides a residual, a contradiction, or an unavailable portion

   An unanswerable question is still a result: CONTEXT_UNRESOLVED renders the
   clarification the engine asked for, and DATA_UNAVAILABLE renders what was
   missing. Neither is styled as an error, because neither is one. */

export interface AskAnswer {
  answer_status: string
  question: string
  short_answer: string
  scope: Record<string, unknown>
  observations: Array<{ statement: string; value: number | null; unit?: string | null; claim_class: string; corroborated_by?: string[] }>
  spatial: Array<{ scope: string; measured_delta_s?: number | null; telemetry_estimated_loss_s?: number | null; note?: string }>
  hypotheses: Array<{ hypothesis_id: string; state: string; supporting_evidence_ids: string[]; contradicting_evidence_ids: string[] }>
  residuals: Array<{ statement: string; value: number; unit?: string }>
  counterfactuals: Array<{ statement: string; value: number; claim_class: string }>
  not_established: Array<{ statement: string; reason: string }>
  limitations: string[]
  missing_evidence: string[]
  engine_conclusion?: string | null
  /* Engineering autopsy (§26). Every event names the capability that produced
     it. materiality separates a change in the car from a change in what we
     could measure — collapsing the two is the failure this panel must not
     repeat. */
  events: AskEvent[]
  /* Disconfirming evidence, resolved to readable statements. A hypothesis with
     no counter-evidence listed has none, which is itself worth showing. */
  counter_evidence: Array<{
    hypothesis_id: string
    evidence_id: string
    statement: string | null
    resolved: boolean
  }>
  answer_mode: string
  provenance: Record<string, unknown>
  follow_ups: Array<{ label: string; capability_id: string; available: boolean }>
}

export interface AskEvent {
  event_id: string
  event_type: string
  lap_start: number
  observed_change: string
  magnitude: number | null
  unit: string | null
  materiality: 'ENGINEERING' | 'MEASUREMENT'
  source_capability: string
  method: string | null
  limitations: string[]
}

/* Decision twin (§40). Every scenario point carries claim_class MODELLED and
   is_historical_truth false; the interface re-states both so no consumer can
   render one without the other. */
export interface TwinPoint {
  fraction: number
  status: string
  delta_lap_time_s: number | null
  claim_class: string
  is_historical_truth: boolean
  validity: string | null
}

export interface TwinResult {
  status: string
  dimension: string
  intervention_type: string
  reason?: string
  scenario_space: TwinPoint[]
  sensitivity: { shape: string; note: string }
  baseline: { claim_class: string; lap_time_s: number | null; source: string }
  limitations: string[]
}

export interface AskClarification {
  field: string
  prompt: string
  candidates: string[]
}

export interface AskResult {
  status: string
  investigation_id: string
  duration_ms: number
  compiled: {
    status: string
    reason?: string | null
    clarifications?: AskClarification[]
    detected_intents?: string[]
    race_label?: string | null
    season?: number | null
    round?: number | null
    driver_a?: string | null
    driver_b?: string | null
  }
  answer: AskAnswer
  autopsy?: {
    status: string
    event_count: number
    material_event_count: number
    events_by_type: Record<string, number>
    source_capabilities: string[]
  } | null
  verification: { passed: boolean; checks_run: number; violations: unknown[] }
}

/* Engine hypothesis states, rendered verbatim. The engine keeps
   CONTRADICTED_OR_NOT_SUPPORTED and UNTESTABLE distinct because "we tested it
   and it did not hold" and "we could not test it" are different facts. */
function hypothesisTone(state: string): string {
  if (state === 'SUPPORTED') return 'rw-chip--supported'
  if (state === 'CONTRADICTED_OR_NOT_SUPPORTED') return 'rw-chip--contradicted'
  if (state === 'UNTESTABLE') return 'rw-chip--unsupported'
  return 'rw-chip--neutral'
}

export default function UniversalQuestion({
  initialContext,
}: {
  initialContext?: Record<string, unknown>
}) {
  const [question, setQuestion] = useState('')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<AskResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [followUp, setFollowUp] = useState('')
  const [twin, setTwin] = useState<TwinResult | null>(null)
  const [twinRunning, setTwinRunning] = useState(false)
  /* Measurement events are hidden by default. They are real and they are
     reported, but leading a race timeline with 46 telemetry-availability
     flips buries the 7 regime changes an engineer came to read. */
  const [showMeasurement, setShowMeasurement] = useState(false)

  const ask = useCallback(async (text: string, context?: Record<string, unknown>) => {
    if (!text.trim()) return
    setRunning(true)
    setError(null)
    try {
      const resp = await fetch('/api/investigations/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: text, context }),
      })
      if (!resp.ok) throw new Error(`engine returned ${resp.status}`)
      setResult((await resp.json()) as AskResult)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'investigation failed')
    } finally {
      setRunning(false)
    }
  }, [])

  const continueWith = useCallback(
    (text: string) => {
      const context = {
        ...(initialContext ?? {}),
        ...(result?.answer.scope ?? {}),
      }
      setFollowUp('')
      void ask(text, context)
    },
    [ask, initialContext, result],
  )

  /* The sweep runs against the resolved investigation scope. If the question
     left no lap pinned there is nothing to intervene on, so the control stays
     disabled rather than guessing a lap. */
  const runSweep = useCallback(async () => {
    const scope = result?.answer.scope ?? {}
    const season = scope.season
    const round = scope.round
    const driver = scope.driver_a
    const reference = scope.driver_b
    const lap = scope.lap_number
    if (
      typeof season !== 'number' ||
      typeof round !== 'number' ||
      typeof driver !== 'string' ||
      typeof lap !== 'number'
    ) {
      return
    }
    setTwinRunning(true)
    try {
      const resp = await fetch('/api/investigations/decision-twin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          season,
          round,
          driver,
          lap_number: lap,
          reference_driver: typeof reference === 'string' ? reference : null,
          session_type: typeof scope.session_type === 'string' ? scope.session_type : 'RACE',
        }),
      })
      if (!resp.ok) throw new Error(`twin returned ${resp.status}`)
      setTwin((await resp.json()) as TwinResult)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'scenario sweep failed')
    } finally {
      setTwinRunning(false)
    }
  }, [result])

  const needsClarification = result?.compiled.status === 'CONTEXT_UNRESOLVED'
  const answer = result?.answer

  /* Defaults mirror how clarifications and follow-ups are already read here:
     a payload from an older build must not blank the whole panel. */
  const allEvents: AskEvent[] = answer?.events ?? []
  const counterEvidence = answer?.counter_evidence ?? []
  const visibleEvents = showMeasurement
    ? allEvents
    : allEvents.filter((e) => e.materiality === 'ENGINEERING')
  const measurementCount = allEvents.filter(
    (e) => e.materiality === 'MEASUREMENT',
  ).length

  /* The sweep needs a pinned lap. Most questions do not carry one. */
  const sweepScope = answer?.scope ?? {}
  const sweepReady =
    typeof sweepScope.season === 'number' &&
    typeof sweepScope.round === 'number' &&
    typeof sweepScope.driver_a === 'string' &&
    typeof sweepScope.lap_number === 'number'

  return (
    <section className="uq" aria-label="Universal question entry">
      <p className="cmd-eyebrow">Ask anything</p>
      <h2 className="uq-headline">Ask RACEWISE about this race.</h2>

      <div className="cmd-ask">
        <textarea
          className="cmd-ask-input"
          rows={2}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey || !e.shiftKey)) {
              e.preventDefault()
              void ask(question, initialContext)
            }
          }}
          aria-label="Ask RACEWISE anything"
          placeholder="Why did Verstappen lose time to Pérez on lap 6 at Bahrain 2023?"
        />
        <button
          className="rw-btn rw-btn--primary rw-btn--lg cmd-ask-go"
          onClick={() => void ask(question, initialContext)}
          disabled={running || !question.trim()}
        >
          {running ? 'Investigating…' : 'Ask RACEWISE'}
        </button>
      </div>

      {error && <p className="uq-error" role="alert">Investigation failed: {error}</p>}

      {result && needsClarification && (
        <div className="uq-card uq-card--clarify">
          <h3 className="uq-h3">One thing to pin down</h3>
          {(result.compiled.clarifications ?? []).map((c) => (
            <div key={c.field} className="uq-clarify">
              <p className="uq-clarify-q">{c.prompt}</p>
              {c.candidates.length > 0 && (
                <div className="uq-clarify-opts">
                  {c.candidates.map((candidate) => (
                    <button
                      key={candidate}
                      className="rw-chip rw-chip--neutral"
                      onClick={() =>
                        void ask(`${question} (${candidate})`, initialContext)
                      }
                    >
                      {candidate}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {answer && !needsClarification && (
        <article className="uq-card">
          <header className="uq-head">
            <span className="rw-chip rw-chip--neutral">{answer.answer_status}</span>
            <p className="uq-short">{answer.short_answer}</p>
          </header>

          {answer.observations.length > 0 && (
            <section className="uq-sec">
              <h3 className="uq-h3">Observed</h3>
              <ul className="uq-list">
                {answer.observations.map((o, i) => (
                  <li key={`${o.statement}-${i}`} className="uq-item">
                    <span className="uq-item-label">{o.statement}</span>
                    <span className="rw-num">
                      {o.value == null ? '—' : o.value.toFixed(3)}
                      {o.unit ? ` ${o.unit}` : ''}
                    </span>
                    {o.corroborated_by && o.corroborated_by.length > 0 && (
                      <span className="uq-item-note">corroborated</span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {answer.spatial.length > 0 && (
            <section className="uq-sec">
              <h3 className="uq-h3">Where</h3>
              <ul className="uq-list">
                {answer.spatial.map((s, i) => (
                  <li key={`${s.scope}-${i}`} className="uq-item">
                    <span className="uq-item-label">{s.scope}</span>
                    <span className="rw-num">
                      {s.measured_delta_s == null
                        ? '—'
                        : `${s.measured_delta_s > 0 ? '+' : ''}${s.measured_delta_s.toFixed(3)} s`}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {answer.hypotheses.length > 0 && (
            <section className="uq-sec">
              <h3 className="uq-h3">Hypotheses</h3>
              <ul className="uq-list">
                {answer.hypotheses.map((h) => (
                  <li key={h.hypothesis_id} className="uq-item">
                    <span className="uq-item-label">{h.hypothesis_id}</span>
                    <span className={`rw-chip ${hypothesisTone(h.state)}`}>{h.state}</span>
                    <span className="uq-item-note">
                      {h.supporting_evidence_ids.length} supporting ·{' '}
                      {h.contradicting_evidence_ids.length} contradicting
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {answer.residuals.length > 0 && (
            <section className="uq-sec">
              <h3 className="uq-h3">Unexplained</h3>
              {answer.residuals.map((r, i) => (
                <p key={i} className="uq-residual">
                  {Math.abs(r.value).toFixed(3)} {r.unit ?? 's'} remains unexplained
                  by the mechanisms tested — reported, never assigned to a cause.
                </p>
              ))}
            </section>
          )}

          {answer.counterfactuals.length > 0 && (
            <section className="uq-sec">
              <h3 className="uq-h3">Modelled</h3>
              {answer.counterfactuals.map((c, i) => (
                <p key={i} className="uq-modelled">
                  {c.statement}: <span className="rw-num">{c.value.toFixed(3)}</span>{' '}
                  <span className="rw-chip rw-chip--unsupported">{c.claim_class}</span>
                </p>
              ))}
            </section>
          )}

          {allEvents.length > 0 && (
            <section className="uq-sec" aria-label="Race timeline">
              <h3 className="uq-h3">
                What changed
                <span className="uq-item-note">
                  {allEvents.length} curated events ·{' '}
                  {allEvents.filter((e) => e.materiality === 'ENGINEERING').length}{' '}
                  engineering
                </span>
              </h3>
              <p className="uq-timeline-note">
                Every event below was reported by a deterministic capability and
                is listed with that capability. The autopsy derives none of them.
              </p>
              <ul className="uq-list uq-timeline">
                {visibleEvents.map((e) => (
                  <li key={e.event_id} className="uq-event" data-materiality={e.materiality}>
                    <span className="uq-event-lap">L{e.lap_start}</span>
                    <span className="uq-event-body">
                      <span className="uq-event-text">{e.observed_change}</span>
                      <span className="uq-item-note">
                        {e.event_type} · {e.source_capability}
                        {e.magnitude != null &&
                          ` · ${e.magnitude.toFixed(3)} ${e.unit ?? ''}`}
                      </span>
                      {e.limitations.map((lim, i) => (
                        <span key={i} className="uq-event-limitation">
                          {lim}
                        </span>
                      ))}
                    </span>
                    <span
                      className={`rw-chip ${
                        e.materiality === 'ENGINEERING'
                          ? 'rw-chip--supported'
                          : 'rw-chip--neutral'
                      }`}
                    >
                      {e.materiality}
                    </span>
                  </li>
                ))}
              </ul>
              {measurementCount > 0 && (
                <button
                  className="rw-chip rw-chip--neutral uq-toggle"
                  aria-label="Show measurement events"
                  aria-pressed={showMeasurement}
                  onClick={() => setShowMeasurement((v) => !v)}
                >
                  {showMeasurement
                    ? 'Hide measurement events'
                    : `Show ${measurementCount} measurement events`}
                </button>
              )}
            </section>
          )}

          {counterEvidence.length > 0 && (
            <section className="uq-sec">
              <h3 className="uq-h3">What contradicts this</h3>
              <ul className="uq-list">
                {counterEvidence.map((c, i) => (
                  <li key={`${c.hypothesis_id}-${c.evidence_id}-${i}`} className="uq-item uq-item--stack">
                    <span className="uq-item-label">
                      {c.statement ?? `${c.evidence_id} (not in the ledger)`}
                    </span>
                    <span className="uq-item-note">
                      against {c.hypothesis_id}
                      {!c.resolved && ' · reference unresolved in ledger'}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="uq-sec" aria-label="What if scenario sweep">
            <h3 className="uq-h3">What if</h3>
            {sweepReady ? (
              <button
                className="rw-btn rw-btn--secondary"
                onClick={() => void runSweep()}
                disabled={twinRunning}
              >
                {twinRunning ? 'Modelling…' : 'Run scenario sweep'}
              </button>
            ) : (
              <p className="uq-item-note">
                A scenario sweep needs a pinned lap. Ask about a specific lap to
                model interventions on it.
              </p>
            )}

            {twin && twin.status !== 'COMPLETED' && twin.status !== 'PARTIALLY_MODELLED' && (
              <div className="uq-twin uq-twin--refused">
                <span className="rw-chip rw-chip--unsupported">{twin.status}</span>
                {twin.reason && <p className="uq-item-note">{twin.reason}</p>}
              </div>
            )}

            {twin && (twin.status === 'COMPLETED' || twin.status === 'PARTIALLY_MODELLED') && (
              <div className="uq-twin">
                <p className="uq-modelled-note">
                  Measured lap time{' '}
                  <span className="rw-num">
                    {twin.baseline.lap_time_s == null
                      ? '—'
                      : `${twin.baseline.lap_time_s.toFixed(3)} s`}
                  </span>{' '}
                  <span className="rw-chip rw-chip--supported">{twin.baseline.claim_class}</span>
                </p>
                <table className="uw-sweep">
                  <caption className="uw-caption">
                    Modelled effect of removing {twin.dimension} · not a prediction
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Fraction</th>
                      <th scope="col">Modelled Δ</th>
                      <th scope="col">Class</th>
                    </tr>
                  </thead>
                  <tbody>
                    {twin.scenario_space.map((p) => (
                      <tr key={p.fraction}>
                        <td>{p.fraction.toFixed(2)}</td>
                        <td className="rw-num">
                          {p.delta_lap_time_s == null ? '—' : `${p.delta_lap_time_s.toFixed(3)} s`}
                        </td>
                        <td>
                          <span className="rw-chip rw-chip--unsupported">{p.claim_class}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="uq-item-note">
                  Response shape: {twin.sensitivity.shape}. {twin.sensitivity.note}
                </p>
                {twin.limitations.map((lim, i) => (
                  <p key={i} className="uq-item-note">
                    {lim}
                  </p>
                ))}
              </div>
            )}
          </section>

          {answer.not_established.length > 0 && (
            <section className="uq-sec">
              <h3 className="uq-h3">Not established</h3>
              <ul className="uq-list">
                {answer.not_established.map((n, i) => (
                  <li key={i} className="uq-item uq-item--stack">
                    <span className="uq-item-label">{n.statement}</span>
                    <span className="uq-item-note">{n.reason}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {answer.engine_conclusion && (
            <section className="uq-sec">
              <h3 className="uq-h3">Engine conclusion</h3>
              <p className="uq-conclusion">{answer.engine_conclusion}</p>
            </section>
          )}

          {answer.follow_ups.length > 0 && (
            <section className="uq-sec">
              <h3 className="uq-h3">Continue</h3>
              <div className="uq-clarify-opts">
                {answer.follow_ups.map((f) => (
                  <button
                    key={f.capability_id + f.label}
                    className="rw-chip rw-chip--neutral"
                    disabled={!f.available}
                    onClick={() => continueWith(f.label)}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
              <div className="cmd-ask uq-followup">
                <input
                  className="rw-input"
                  value={followUp}
                  onChange={(e) => setFollowUp(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') continueWith(followUp)
                  }}
                  aria-label="Follow-up question"
                  placeholder="Ask a follow-up…"
                />
                <button
                  className="rw-btn rw-btn--secondary"
                  disabled={!followUp.trim() || running}
                  onClick={() => continueWith(followUp)}
                >
                  Ask
                </button>
              </div>
            </section>
          )}

          <footer className="uq-foot">
            <span className="rw-k">{result?.verification.passed ? 'VERIFIED' : 'UNVERIFIED'}</span>
            <span className="uq-item-note">
              {result?.verification.checks_run} grounding checks ·{' '}
              {result?.duration_ms} ms
            </span>
          </footer>
        </article>
      )}
    </section>
  )
}