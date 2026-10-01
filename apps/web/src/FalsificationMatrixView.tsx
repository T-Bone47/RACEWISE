import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { HYP_LABELS, QUESTION_INPUTS } from './types'
import type { InvestigationResult, LedgerItem } from './types'
import { Drawer, EvidenceDetails, LoadingLine, StateChip, StructuredError, WorkspaceSkeleton } from './workspace'

/* ============ Stitch Falsification Matrix — the real 6N hypothesis system ============
   Renders the canonical H1–H6 falsification protocol from the deterministic
   engineering investigation. The matrix layout follows the Stitch screen:
   hypothesis + theoretical claim | falsification criterion | empirical
   evidence | verdict. Every verdict, evidence id and count comes from the
   engine payload; the criterion column renders the engine's documented
   deterministic evaluation rules (methodology, not data).
   ==================================================================================== */

/* The six canonical hypothesis statements mirror evidence_fusion.py
   (HYPOTHESES) — engine methodology constants, pinned by contract tests.
   The evaluation rules mirror evaluate_hypothesis()'s documented rule set. */
const HYPOTHESIS_STATEMENTS: Record<string, string> = {
  H1_corner_speed:
    "Driver B's deficit arises primarily from lower speed through corners/fast sections",
  H2_throttle:
    "Driver B's deficit is associated with later/reduced throttle application",
  H3_braking:
    "Driver B's deficit arises from braking differences (more/later braking)",
  H4_tyre_state:
    'A tyre-state difference (compound or age) explains part of the deficit',
  H5_race_control:
    'Race-control restriction, pit interference or conditions explain the delta',
  H6_drs:
    "Lower DRS availability contributed to Driver B's deficit",
}

const EVALUATION_RULES: Record<string, { required: string; criterion: string }> = {
  H1_corner_speed: { required: 'speed region / speed metric evidence', criterion: 'contradicted when valid brake-metric evidence conflicts with the speed-region claim' },
  H2_throttle: { required: 'throttle evidence', criterion: 'contradicted when valid throttle evidence conflicts with the throttle-application claim' },
  H3_braking: { required: 'brake evidence', criterion: 'contradicted when valid brake evidence conflicts with the braking claim' },
  H4_tyre_state: { required: 'tyre-state evidence', criterion: 'contradicted when valid tyre-state evidence conflicts with the compound/age claim' },
  H5_race_control: { required: 'race-control evidence', criterion: 'contradicted by race-control, pit or weather evidence conflicting with the restriction claim' },
  H6_drs: { required: 'DRS evidence', criterion: 'contradicted when valid DRS evidence conflicts with the DRS-availability claim' },
}

const GATE_RULE_SUMMARY =
  'NOT_TESTABLE without required-source evidence · CONTRADICTED on any valid contradiction · ' +
  'SUPPORTED needs supporting evidence and zero contradictions · PARTIALLY_SUPPORTED adds ' +
  'non-decisive evidence · NOT_SUPPORTED when tested evidence fails to support. ' +
  'Evidence-consistency, never proof; causation is never asserted.'

type Filter = 'ALL' | 'CONTRADICTED'

export default function FalsificationMatrixView({ presetParams }: { presetParams?: URLSearchParams }) {
  const [questionType] = useState(() => presetParams?.get('question_type') || 'HYPOTHESIS_EVALUATION')
  const [season] = useState(() => Number(presetParams?.get('season') || 2023))
  const [round] = useState(() => Number(presetParams?.get('round') || 1))
  const [driverA] = useState(() => presetParams?.get('driver_a') || 'max-verstappen')
  const [driverB] = useState(() => presetParams?.get('driver_b') || 'sergio-perez')
  const [lapNumber] = useState(() => Number(presetParams?.get('lap_number') || 6))
  const [sessionType] = useState(() => presetParams?.get('session_type') || 'RACE')

  const [result, setResult] = useState<InvestigationResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<{ code: string; message: string } | null>(null)
  const [filter, setFilter] = useState<Filter>('ALL')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [drawerItem, setDrawerItem] = useState<LedgerItem | null>(null)

  const inputs = QUESTION_INPUTS[questionType] || []

  const scopeParams = useMemo(() => {
    const p = new URLSearchParams({
      question_type: questionType,
      driver_a: driverA,
      driver_b: driverB,
      season: String(season),
      round: String(round),
      session_type: sessionType,
    })
    if (inputs.includes('lap_number') && lapNumber >= 1) p.set('lap_number', String(lapNumber))
    return p
  }, [questionType, driverA, driverB, season, round, sessionType, lapNumber, inputs])

  const run = useCallback(async () => {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const resp = await fetch(`/api/catalog/engineering-investigation?${scopeParams}`)
      if (!resp.ok) {
        const detail = await resp.json().catch(() => null)
        throw new Error(detail?.detail || `Investigation request failed (${resp.status})`)
      }
      const j = (await resp.json()) as InvestigationResult
      if (j.status !== 'VALID') {
        setError({ code: j.status || 'UNAVAILABLE', message: j.reason || `status ${j.status}` })
        return
      }
      setResult(j)
    } catch (e) {
      setError({ code: 'NETWORK', message: e instanceof Error ? e.message : String(e) })
    } finally {
      setLoading(false)
    }
  }, [scopeParams])

  useEffect(() => { void run() }, [run])

  const evaluations = useMemo(
    () => Object.values(result?.hypothesis_evaluations ?? {}),
    [result],
  )
  const counts = useMemo(() => {
    const c = { total: evaluations.length, contradicted: 0, supported: 0, partial: 0, untested: 0, other: 0 }
    for (const h of evaluations) {
      if (h.aggregate_state === 'CONTRADICTED') c.contradicted++
      else if (h.aggregate_state === 'SUPPORTED') c.supported++
      else if (h.aggregate_state === 'PARTIALLY_SUPPORTED' || h.aggregate_state === 'MIXED_EVIDENCE') c.partial++
      else if (h.aggregate_state === 'NOT_TESTABLE' || h.aggregate_state === 'INSUFFICIENT_EVIDENCE') c.untested++
      else c.other++
    }
    return c
  }, [evaluations])

  const rows = useMemo(
    () => (filter === 'CONTRADICTED'
      ? evaluations.filter((h) => h.aggregate_state === 'CONTRADICTED')
      : evaluations),
    [evaluations, filter],
  )

  const ledgerById = useMemo(() => {
    const m = new Map<string, LedgerItem>()
    for (const it of result?.evidence_ledger ?? []) m.set(it.evidence_id, it)
    return m
  }, [result])

  function evidenceChips(ids: string[], tone: 'supporting' | 'contradicting' | 'non-decisive') {
    if (ids.length === 0) return <span className="muted small">none</span>
    return (
      <span className={`fm-ev-chips fm-${tone}`}>
        {ids.map((id) => (
          <button
            key={id}
            className="fm-ev-chip"
            title={(ledgerById.get(id)?.claim ?? 'open evidence detail')}
            onClick={() => {
              const item = ledgerById.get(id)
              if (item) setDrawerItem(item)
            }}
          >
            {id}
          </button>
        ))}
      </span>
    )
  }

  return (
    <div className="fm-layout">
      {/* ============ protocol banner ============ */}
      <section className="fm-banner" aria-label="Falsification protocol">
        <div className="fm-banner-head">
          <div>
            <span className="t-microlabel">Falsification protocol · deterministic evaluation rules</span>
            <h2 className="fm-title">
              Falsification — what empirical evidence refutes each hypothesis?
            </h2>
            <p className="muted small">
              {questionType.replace(/_/g, ' ').toLowerCase()} · {driverA} vs {driverB} ·{' '}
              {season} R{round}
              {inputs.includes('lap_number') && lapNumber >= 1 ? ` · lap ${lapNumber}` : ''}
              {result && (
                <>
                  {' '}· <span className="mono" title="canonical investigation id">{result.investigation_id}</span>
                </>
              )}
            </p>
          </div>
          {result && <StateChip state={result.synthesis.conclusion_state} />}
        </div>

        {/* real protocol counts from the payload */}
        <div className="fm-cards" role="list" aria-label="Protocol summary">
          <div className="fm-card" role="listitem">
            <span className="m-label">Hypotheses in scope</span>
            <span className="m-value">{counts.total}</span>
            <span className="m-sub">canonical H1–H6 states</span>
          </div>
          <div className="fm-card" role="listitem">
            <span className="m-label">Contradicted</span>
            <span className="m-value rg-wider">{counts.contradicted}</span>
            <span className="m-sub">valid evidence conflicts</span>
          </div>
          <div className="fm-card" role="listitem">
            <span className="m-label">Supported</span>
            <span className="m-value rg-narrowing">{counts.supported}</span>
            <span className="m-sub">evidence-consistent, not proven</span>
          </div>
          <div className="fm-card" role="listitem">
            <span className="m-label">Partial / insufficient</span>
            <span className="m-value">{counts.partial + counts.untested + counts.other}</span>
            <span className="m-sub">mixed, untestable or insufficient</span>
          </div>
        </div>

        <div className="fm-controls">
          <button
            className={filter === 'ALL' ? 'primary' : ''}
            onClick={() => setFilter('ALL')}
            aria-pressed={filter === 'ALL'}
          >
            ALL ({counts.total})
          </button>
          <button
            className={filter === 'CONTRADICTED' ? 'primary' : ''}
            onClick={() => setFilter('CONTRADICTED')}
            aria-pressed={filter === 'CONTRADICTED'}
          >
            CONTRADICTED ({counts.contradicted})
          </button>
          <span className="spacer" />
          <button onClick={() => void run()} disabled={loading}>
            {loading ? 'Re-running…' : 'Re-run investigation (deterministic)'}
          </button>
        </div>
      </section>

      {error && (
        <StructuredError
          code={error.code}
          message={error.message}
          hint="The matrix renders only evaluated evidence — nothing is broadened silently."
        />
      )}
      {loading && <WorkspaceSkeleton />}
      {!result && !loading && !error && <LoadingLine label="Waiting for the investigation…" />}

      {result && (
        <div className="fm-body">
          {/* ============ the matrix ============ */}
          <section className="panel fm-matrix-panel" aria-label="Falsification matrix">
            <table className="catalog-table fm-table">
              <thead>
                <tr>
                  <th scope="col">ID</th>
                  <th scope="col">Hypothesis & theoretical claim</th>
                  <th scope="col">Falsification criterion (engine rule)</th>
                  <th scope="col">Empirical evidence evaluated</th>
                  <th scope="col">Verdict</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((h) => {
                  const statement = HYPOTHESIS_STATEMENTS[h.hypothesis_id] ?? h.hypothesis_id
                  const rule = EVALUATION_RULES[h.hypothesis_id]
                  const open = expanded === h.hypothesis_id
                  return (
                    <Fragment key={h.hypothesis_id}>
                      <tr
                        className={`clickable ${open ? 'selected' : ''}`}
                        onClick={() => setExpanded(open ? null : h.hypothesis_id)}
                        aria-expanded={open}
                      >
                        <td className="mono small">{HYP_LABELS[h.hypothesis_id]?.split(' ')[0] ?? h.hypothesis_id}</td>
                        <td>
                          <div className="fm-hyp">{HYP_LABELS[h.hypothesis_id] ?? h.hypothesis_id}</div>
                          <div className="muted small">{statement}</div>
                        </td>
                        <td className="small">
                          <div>requires: {rule?.required ?? '—'}</div>
                          <div className="muted">{rule?.criterion ?? '—'}</div>
                        </td>
                        <td>
                          <div className="fm-ev">
                            <span className="t-microlabel">supporting ({h.evidence_coverage.supporting})</span>
                            {evidenceChips(h.supporting_evidence, 'supporting')}
                          </div>
                          <div className="fm-ev">
                            <span className="t-microlabel">contradicting ({h.evidence_coverage.contradicting})</span>
                            {evidenceChips(h.contradicting_evidence, 'contradicting')}
                          </div>
                          <div className="fm-ev">
                            <span className="t-microlabel">non-decisive ({h.evidence_coverage.non_decisive})</span>
                            {evidenceChips(h.non_decisive_evidence, 'non-decisive')}
                          </div>
                        </td>
                        <td>
                          <StateChip state={h.aggregate_state} />
                          <div className="muted small" title="falsification gate status">
                            gate: {h.falsification_status.toLowerCase()}
                          </div>
                        </td>
                      </tr>
                      {open && (
                        <tr key={`${h.hypothesis_id}-detail`} className="fm-detail-row">
                          <td colSpan={5}>
                            <div className="fm-detail">
                              {/* mission §15: the scientific test, explicit */}
                              <div className="fm-detail-sec">
                                <span className="t-microlabel">Prediction (engine statement)</span>
                                <span className="small">{statement}</span>
                              </div>
                              <div className="fm-detail-sec">
                                <span className="t-microlabel">Evidence tested</span>
                                <span className="small muted">
                                  {h.evidence_coverage.items_total} evaluated item(s) —{' '}
                                  {h.supporting_evidence.length} supporting · {h.contradicting_evidence.length} contradicting ·{' '}
                                  {h.non_decisive_evidence.length} non-decisive
                                </span>
                              </div>
                              <div className="fm-detail-sec">
                                <span className="t-microlabel">Observation (evaluated evidence)</span>
                                {[...h.supporting_evidence, ...h.contradicting_evidence, ...h.non_decisive_evidence]
                                  .map((id) => ledgerById.get(id))
                                  .filter((it): it is LedgerItem => it != null)
                                  .map((it) => (
                                    <div key={it.evidence_id} className="fm-ev-item small">
                                      <button className="linklike mono" onClick={() => setDrawerItem(it)}>
                                        {it.evidence_id}
                                      </button>
                                      <span className={`claim-tag tag-${it.claim_class}`}>{it.claim_class}</span>
                                      <span>{it.claim}</span>
                                      {it.measured_value != null && (
                                        <span className="mono"> = {typeof it.measured_value === 'number' ? it.measured_value : JSON.stringify(it.measured_value)} {it.units ?? ''}</span>
                                      )}
                                      <StateChip state={it.state} />
                                    </div>
                                  ))}
                              </div>
                              <div className="fm-detail-sec">
                                <span className="t-microlabel">Contradictions</span>
                                {h.contradicting_evidence.length > 0 ? (
                                  <span className="small rg-warn">
                                    {h.contradicting_evidence.join(', ')} — preserved, never resolved away
                                  </span>
                                ) : (
                                  <span className="small muted">
                                    none found in the evaluated evidence — an observation about this ledger, not a confirmation
                                  </span>
                                )}
                              </div>
                              <div className="fm-detail-sec">
                                <span className="t-microlabel">Result</span>
                                <span className="small">
                                  <StateChip state={h.aggregate_state} /> · falsification gate: {h.falsification_status.toLowerCase()}
                                </span>
                              </div>
                              <div className="fm-detail-sec">
                                <span className="t-microlabel">What would falsify this</span>
                                <span className="small muted">
                                  requires: {rule?.required ?? '—'} — {rule?.criterion ?? '—'}
                                </span>
                              </div>
                              {h.supporting_evidence.length + h.contradicting_evidence.length + h.non_decisive_evidence.length === 0 && (
                                <div className="empty-state">
                                  No evaluated evidence for this hypothesis — the state stays
                                  honest (NOT_TESTABLE / INSUFFICIENT_EVIDENCE), never guessed.
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
                {rows.length === 0 && (
                  <tr><td colSpan={5} className="muted small">no hypothesis matches this filter</td></tr>
                )}
              </tbody>
            </table>
            <p className="muted small">{GATE_RULE_SUMMARY}</p>
            <button
              className="linklike small"
              onClick={() => {
                const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
                const url = URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url
                a.download = `racewise-falsification-${result.investigation_id}.json`
                a.click()
                URL.revokeObjectURL(url)
              }}
            >
              export the verbatim evaluation payload (JSON)
            </button>
          </section>

          {/* ============ decision trace rail ============ */}
          <section className="panel fm-trace-panel" aria-label="Decision trace">
            <h2>Decision trace — deterministic sequence</h2>
            <ol className="fm-trace">
              {result.decision_trace.map((t, i) => (
                <li key={t.trace_id} className="fm-trace-step">
                  <span className="fm-trace-num mono">{String(i + 1).padStart(2, '0')}</span>
                  <div className="fm-trace-body">
                    <div className="fm-trace-head">
                      <span className="mono small">{t.trace_id}</span>
                      <StateChip state={t.status} />
                    </div>
                    <p className="small">{t.statement}</p>
                    {t.basis.length > 0 && (
                      <div className="muted small">
                        basis: {t.basis.map((b) => (
                          <button
                            key={b}
                            className="linklike small mono"
                            onClick={() => {
                              const item = ledgerById.get(b)
                              if (item) setDrawerItem(item)
                            }}
                          >
                            {b}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ol>
            <div className="fm-boundaries">
              <strong className="small">Epistemic boundaries (engine-enforced)</strong>
              <ul className="small">
                {result.epistemic_boundaries.slice(0, 8).map((b) => <li key={b} className="muted">{b}</li>)}
              </ul>
            </div>
          </section>
        </div>
      )}

      {/* ============ synthesis bar ============ */}
      {result && (
        <section className="fm-synthesis" aria-label="Synthesis">
          <div>
            <span className="t-microlabel">Synthesis ({result.synthesis.conclusion_state.replace(/_/g, ' ').toLowerCase()})</span>
            <p className="small">
              {result.synthesis.unresolved_questions.length > 0
                ? result.synthesis.unresolved_questions.join(' · ')
                : 'No unresolved question blocks the synthesis for the evaluated evidence — an observation about this ledger, not a confirmation.'}
            </p>
            <p className="muted small">
              Verdicts are evidence-consistency statements. The engine never ranks
              hypotheses, never isolates a single “primary cause”, and never assigns
              the residual to a mechanism.
            </p>
          </div>
          <div className="fm-synthesis-actions">
            <button
              onClick={() => {
                const p = new URLSearchParams({
                  question_type: questionType,
                  driver_a: driverA,
                  driver_b: driverB,
                  season: String(season),
                  round: String(round),
                  session_type: sessionType,
                })
                if (inputs.includes('lap_number') && lapNumber >= 1) p.set('lap_number', String(lapNumber))
                window.location.hash = `#/investigate?${p.toString()}`
                window.dispatchEvent(new HashChangeEvent('hashchange'))
              }}
            >
              Open full investigation workspace
            </button>
          </div>
        </section>
      )}

      {/* ============ evidence drawer (real ledger entry) ============ */}
      {drawerItem && (
        <Drawer
          title={`Evidence ${drawerItem.evidence_id}`}
          subtitle={`${drawerItem.source_phase} · ${drawerItem.source_tool}`}
          onClose={() => setDrawerItem(null)}
        >
          <EvidenceDetails item={drawerItem} />
        </Drawer>
      )}
    </div>
  )
}
