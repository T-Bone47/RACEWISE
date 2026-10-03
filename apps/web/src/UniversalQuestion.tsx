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
  provenance: Record<string, unknown>
  follow_ups: Array<{ label: string; capability_id: string; available: boolean }>
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

  const needsClarification = result?.compiled.status === 'CONTEXT_UNRESOLVED'
  const answer = result?.answer

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