import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  HYP_LABELS, QUESTION_INPUTS, QUESTION_TYPES,
} from './types'
import type { InvestigationResult, LedgerItem } from './types'
import { StructuredError, WorkspaceSkeleton } from './workspace'
import { ClaimTag, ContextInspector, StateChip } from './workspace'
import type { InspectorEntry, ProvenanceTarget } from './workspace'
import { GraphPanel, ReplayPanel, ComparePanel, MemoryPanel } from './panels'
import { saveRecent } from './CommandCenterView'
import type { RecentInvestigation } from './CommandCenterView'

/* ============ 6Q — Investigation Workspace (upgraded InvestigationView) ============
   One screen: header → hypothesis matrix → evidence ledger + decision trace →
   graph → counterfactuals → provenance. Cross-navigation between all blocks.
   ================================================================================= */

export default function InvestigationView({ presetParams }: { presetParams?: URLSearchParams }) {
  /* question state (from launcher preset when present) */
  const [questionType, setQuestionType] = useState(() => presetParams?.get('question_type') || 'LAP_PERFORMANCE')
  const [season, setSeason] = useState(() => Number(presetParams?.get('season') || 2023))
  const [round, setRound] = useState(() => Number(presetParams?.get('round') || 1))
  const [driverA, setDriverA] = useState(() => presetParams?.get('driver_a') || 'max-verstappen')
  const [driverB, setDriverB] = useState(() => presetParams?.get('driver_b') || 'sergio-perez')
  const [lapNumber, setLapNumber] = useState(() => Number(presetParams?.get('lap_number') || 6))
  const [stintNumber, setStintNumber] = useState(() => Number(presetParams?.get('stint_number') || 1))
  const [patternId, setPatternId] = useState(() => presetParams?.get('pattern_id') || '')
  const [sessionType, setSessionType] = useState(() => presetParams?.get('session_type') || 'RACE')
  const [hypothesesFilter] = useState(() => presetParams?.get('hypotheses') || '')

  const [result, setResult] = useState<InvestigationResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<{ code: string; message: string } | null>(null)

  /* focus + cross-navigation */
  const [hypFilter, setHypFilter] = useState('')
  const [focusNode, setFocusNode] = useState<{ type: string; key: string } | null>(null)
  const [openTrace, setOpenTrace] = useState<string | null>(null)
  /* contextual inspector state: single side-by-side surface with a back stack
     (evidence → trace-to-source → BACK returns to the evidence) */
  const [inspector, setInspector] = useState<InspectorEntry | null>(null)
  const [inspectorHistory, setInspectorHistory] = useState<InspectorEntry[]>([])

  function pushInspector(next: InspectorEntry) {
    setInspectorHistory((h) => {
      const top = h[h.length - 1]
      /* replace-tail semantics: clicking a new object while one is open swaps
         the top; trace-to-source-style drills append below via two-step call */
      if (top && (
        (top.kind === 'evidence' && next.kind === 'evidence' && top.item.evidence_id === next.item.evidence_id) ||
        (top.kind === 'provenance' && next.kind === 'provenance' && top.target.id === next.target.id)
      )) return h
      /* drill-down: provenance opened while an evidence is showing appends */
      if (next.kind === 'provenance' && top && top.kind === 'evidence' &&
          next.target.kind === 'EVIDENCE' && next.target.id === top.item.evidence_id) {
        return [...h, next]
      }
      return [next]
    })
    setInspector(next)
  }

  const inputs = QUESTION_INPUTS[questionType] || []

  const scopeParams = useCallback(() => {
    const params = new URLSearchParams({
      question_type: questionType,
      driver_a: driverA.trim(),
      driver_b: driverB.trim(),
      season: String(season),
      round: String(round),
      session_type: sessionType,
    })
    if (inputs.includes('lap_number') && lapNumber >= 1) params.set('lap_number', String(lapNumber))
    if (inputs.includes('stint_number') && stintNumber >= 1) params.set('stint_number', String(stintNumber))
    if (inputs.includes('pattern_id') && patternId.trim()) params.set('pattern_id', patternId.trim())
    if (hypothesesFilter) params.set('hypotheses', hypothesesFilter)
    return params
  }, [questionType, driverA, driverB, season, round, lapNumber, stintNumber, patternId, hypothesesFilter, inputs, sessionType])

  const run = useCallback(async () => {
    setLoading(true)
    setError(null)
    setResult(null)
    setOpenTrace(null)
    setFocusNode(null)
    try {
      const resp = await fetch(`/api/catalog/engineering-investigation?${scopeParams()}`)
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
      saveRecent({
        investigation_id: j.investigation_id,
        question_type: j.question_type,
        scope: { ...j.question.scope, question_type: j.question_type },
        output_hash: j.output_hash,
        conclusion_state: j.synthesis.conclusion_state,
        evidence_count: j.evidence_ledger.length,
        at: Date.now(),
      } as RecentInvestigation)
    } catch (e) {
      setError({ code: 'NETWORK', message: e instanceof Error ? e.message : String(e) })
    } finally {
      setLoading(false)
    }
  }, [scopeParams])

  /* auto-run when arriving with a launcher preset */
  useEffect(() => {
    if (presetParams && presetParams.get('question_type')) {
      void run()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function focusHypothesis(h: string) {
    setHypFilter(h)
    setFocusNode({ type: 'HYPOTHESIS', key: h })
  }

  function focusEvidence(eid: string) {
    setHypFilter('')
    setFocusNode({ type: 'EVIDENCE', key: eid })
    const item = result?.evidence_ledger.find((x) => x.evidence_id === eid)
    if (item) pushInspector({ kind: 'evidence', item })
  }

  /* evidence ledger filtering */
  const ledger = result?.evidence_ledger ?? []
  const filteredLedger = useMemo(() => ledger.filter((it) => {
    if (hypFilter && !it.hypothesis_ids.includes(hypFilter)) return false
    return true
  }), [ledger, hypFilter])

  const conflictIds = useMemo(
    () => new Set((result?.evidence_conflicts ?? []).flatMap((c) => c.evidence_ids)),
    [result],
  )

  const established = result?.synthesis.conclusion_state === 'SUPPORTED_BY_AVAILABLE_EVIDENCE'
  const blocked = result?.falsification_gate.hypotheses_with_unresolved_contradictions ?? []

  /* every provenance opener routes into the side-by-side inspector */
  function openProvenance(target: ProvenanceTarget) {
    pushInspector({ kind: 'provenance', target })
  }

  /* trace-to-source inside the inspector PUSHES a provenance entry so BACK
     returns to the evidence that was open */
  function inspectorTraceToSource(item: LedgerItem) {
    openProvenance({
      kind: 'EVIDENCE',
      id: item.evidence_id,
      provenance: {
        source_phase: item.source_phase,
        source_tool: item.source_tool,
        source_hash: item.source_hash,
      },
      canonicalReference: item.source_reference,
      assumptions: item.assumptions,
      limitations: item.limitations,
    })
  }

  return (
    <div className={inspector ? 'inv-layout with-inspector' : 'inv-layout'}>
      <div className="inv-main">
      {/* ================= INVESTIGATION HEADER (§8) ================= */}
      <div className="inv-header">
        <div className="inv-title">
          <strong>Investigation workspace</strong>
          {result && <span className="qid mono">{result.investigation_id}</span>}
          {result && <StateChip state={result.synthesis.conclusion_state} />}
          <span className="spacer" />
          {/* §35: investigation → catalog handoff preserving season/round/session */}
          {result && (
            <button
              onClick={() => {
                window.location.hash =
                  `#/catalog?season=${result.question.scope.season}` +
                  `&round=${result.question.scope.round}` +
                  `&session_type=${encodeURIComponent(result.question.scope.session_type)}`
                window.dispatchEvent(new HashChangeEvent('hashchange'))
              }}
            >
              Open race in catalog →
            </button>
          )}
          <button onClick={run} disabled={loading} className="primary">
            {loading ? 'Investigating…' : result ? 'Re-run investigation' : 'Run investigation'}
          </button>
        </div>

        <div className="controls" style={{ marginBottom: result ? 6 : 0 }}>
          <label>
            question type:{' '}
            <select value={questionType} onChange={(e) => setQuestionType(e.target.value)}>
              {QUESTION_TYPES.map((q) => <option key={q} value={q}>{q}</option>)}
            </select>
          </label>
          <label>
            season:{' '}
            <input type="number" min={1950} max={2100} value={season} style={{ width: 80 }}
                   onChange={(e) => setSeason(Number(e.target.value))} />
          </label>
          <label>
            round:{' '}
            <input type="number" min={1} max={99} value={round} style={{ width: 60 }}
                   onChange={(e) => setRound(Number(e.target.value))} />
          </label>
          <label>
            session:{' '}
            <select
              value={sessionType}
              onChange={(e) => {
                setSessionType(e.target.value)
                /* a qualifying session has no stint semantics */
                if (e.target.value === 'QUALIFYING' && questionType === 'STINT_PERFORMANCE') {
                  setQuestionType('LAP_PERFORMANCE')
                }
              }}
            >
              <option value="RACE">Race</option>
              <option value="QUALIFYING">Qualifying (2018+)</option>
            </select>
          </label>
          <label>
            driver A:{' '}
            <input type="text" value={driverA} style={{ width: 145 }}
                   onChange={(e) => setDriverA(e.target.value)} />
          </label>
          <label>
            driver B:{' '}
            <input type="text" value={driverB} style={{ width: 145 }}
                   onChange={(e) => setDriverB(e.target.value)} />
          </label>
          {inputs.includes('lap_number') && (
            <label>
              lap:{' '}
              <input type="number" min={1} value={lapNumber} style={{ width: 60 }}
                     onChange={(e) => setLapNumber(Number(e.target.value))} />
            </label>
          )}
          {inputs.includes('stint_number') && (
            <label>
              stint:{' '}
              <input type="number" min={1} value={stintNumber} style={{ width: 60 }}
                     onChange={(e) => setStintNumber(Number(e.target.value))} />
            </label>
          )}
          {inputs.includes('pattern_id') && (
            <label>
              pattern id:{' '}
              <input type="text" value={patternId} style={{ minWidth: 210 }}
                     onChange={(e) => setPatternId(e.target.value)} />
            </label>
          )}
        </div>

        {result && (
          <div className="inv-meta">
            <span>{result.question_type}</span>
            <span>{result.question.scope.season} R{result.question.scope.round}</span>
            <span>{result.question.scope.driver_a} vs {result.question.scope.driver_b}</span>
            {result.question.scope.lap_number != null && <span>lap {result.question.scope.lap_number}</span>}
            {result.question.scope.stint_number != null && <span>stint {result.question.scope.stint_number}</span>}
            <span>session {result.question.scope.session_type}</span>
            <span>{result.evidence_ledger.length} evidence items</span>
            <span title={`output hash ${result.output_hash}`}>hash <code>{result.output_hash.slice(0, 10)}</code></span>
            <button
              className="linklike small"
              onClick={() => openProvenance({
                kind: 'INVESTIGATION',
                id: result.investigation_id,
                provenance: result.provenance as unknown as Record<string, unknown>,
                canonicalReference: {
                  investigation_version: result.investigation_version,
                  output_hash: result.output_hash,
                  snapshot_evidence_ids: result.investigation_snapshot.evidence_ids.length,
                },
                limitations: result.synthesis.limitations,
              })}
            >
              provenance drawer
            </button>
          </div>
        )}
      </div>

      {error && (
        <StructuredError
          code={error.code}
          message={error.message}
          hint="Adjust the scope or pick a session with the required capability — nothing is broadened silently."
        />
      )}
      {loading && <WorkspaceSkeleton />}

      {!result && !loading && !error && (
        <div className="empty-state">
          No investigation selected. Choose a question type and scope above, or
          start from the command center. Every conclusion here will be bound to
          evidence with a decision trace.
        </div>
      )}

      {result && (
        <>
          {/* ================= FALSIFICATION PANEL (§13) ================= */}
          {(blocked.length > 0 || established) && (
            <div className={`falsification-banner ${blocked.length > 0 ? '' : 'falsification-ok'}`}>
              {blocked.length > 0 ? (
                <>
                  <strong>Unresolved contradictions block an established explanation for:</strong>{' '}
                  {blocked.map((h) => HYP_LABELS[h] || h).join(', ')} — the evidence
                  conflict is preserved, never resolved away.
                </>
              ) : (
                <>
                  <strong>NO_FALSIFICATION_FOUND.</strong> The evaluated evidence did not
                  contradict the hypotheses that reached an established state — that is
                  not confirmation.
                </>
              )}
            </div>
          )}

          {/* ================= HYPOTHESIS MATRIX (§9) ================= */}
          <section className="panel" aria-label="Hypothesis matrix">
            <h2>Hypothesis matrix (never ranked)</h2>
            <table className="catalog-table">
              <thead>
                <tr>
                  <th scope="col">Hypothesis</th>
                  <th scope="col">Evidence</th>
                  <th scope="col">Supporting</th>
                  <th scope="col">Contradicting</th>
                  <th scope="col">Non-decisive</th>
                  <th scope="col">Falsification</th>
                  <th scope="col">State</th>
                </tr>
              </thead>
              <tbody>
                {Object.values(result.hypothesis_evaluations).map((h) => (
                  <tr
                    key={h.hypothesis_id}
                    className={`clickable ${hypFilter === h.hypothesis_id ? 'selected' : ''}`}
                    onClick={() => focusHypothesis(h.hypothesis_id)}
                  >
                    <td className="small">{HYP_LABELS[h.hypothesis_id] || h.hypothesis_id}</td>
                    <td>{h.evidence_coverage.items_total}</td>
                    <td>{h.evidence_coverage.supporting}</td>
                    <td>{h.evidence_coverage.contradicting}</td>
                    <td>{h.evidence_coverage.non_decisive}</td>
                    <td className="small">{h.falsification_status}</td>
                    <td><StateChip state={h.aggregate_state} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted small">{result.falsification_gate.rule}</p>
            <button
              className="linklike small"
              onClick={() => openProvenance({
                kind: 'FALSIFICATION',
                id: 'gate',
                provenance: {
                  source: '6n hypothesis_evaluations + falsification_gate',
                  any_unresolved_contradictions: result.falsification_gate.any_unresolved_contradictions,
                  establishable_hypotheses: result.falsification_gate.establishable_hypotheses,
                },
                limitations: [
                  'an established state is evidence-consistency, never proof',
                  'a hypothesis with unresolved contradictions is not synthesized',
                ],
              })}
            >
              open falsification provenance
            </button>
          </section>

          {/* ================= EVIDENCE LEDGER + DECISION TRACE (§10/§12) ================= */}
          <div className="split">
            <section className="panel" aria-label="Evidence ledger">
              <h2>Evidence ledger ({filteredLedger.length}/{ledger.length})</h2>
              <div className="controls">
                <label>
                  hypothesis:{' '}
                  <select value={hypFilter} onChange={(e) => setHypFilter(e.target.value)}>
                    <option value="">all</option>
                    {Object.keys(HYP_LABELS).map((h) => (
                      <option key={h} value={h}>{HYP_LABELS[h]}</option>
                    ))}
                  </select>
                </label>
              </div>
              <table className="catalog-table">
                <thead>
                  <tr>
                    <th scope="col">ID</th>
                    <th scope="col">Type / class</th>
                    <th scope="col">Source</th>
                    <th scope="col">Claim</th>
                    <th scope="col">State</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredLedger.map((it) => (
                    <tr
                      key={it.evidence_id}
                      className={`clickable ${conflictIds.has(it.evidence_id) ? 'selected' : ''}`}
                      onClick={() => {
                        pushInspector({ kind: 'evidence', item: it })
                        focusEvidence(it.evidence_id)
                      }}
                    >
                      <td className="small"><code>{it.evidence_id}</code></td>
                      <td className="small"><ClaimTag claimClass={it.claim_class} />{it.evidence_type}</td>
                      <td className="muted small" title={`source hash ${it.source_hash}`}>
                        {it.source_phase} {it.source_tool}
                      </td>
                      <td className="small">
                        {it.claim}
                        {it.measured_value != null && (
                          <span className="muted"> = {typeof it.measured_value === 'number' ? it.measured_value : '…'} {it.units ?? ''}</span>
                        )}
                      </td>
                      <td><StateChip state={it.state} /></td>
                    </tr>
                  ))}
                  {filteredLedger.length === 0 && (
                    <tr><td colSpan={5} className="muted small">no evidence matches this filter</td></tr>
                  )}
                </tbody>
              </table>
              <p className="muted small">
                highlighted rows take part in a preserved contradiction · filters sync with
                the hypothesis matrix and the graph
              </p>
            </section>

            <section className="panel" aria-label="Decision trace">
              <h2>Decision trace ({result.decision_trace.length})</h2>
              <ul className="ef-chain">
                {result.decision_trace.map((t) => (
                  <li key={t.trace_id}>
                    <button
                      className="linklike"
                      onClick={() => setOpenTrace(openTrace === t.trace_id ? null : t.trace_id)}
                      aria-expanded={openTrace === t.trace_id}
                    >
                      {t.trace_id}
                    </button>{' '}
                    <span className="small">{t.statement}</span> <StateChip state={t.status} />
                    {openTrace === t.trace_id && (
                      <div className="cf-intervention">
                        <div><strong>type:</strong> {t.type}</div>
                        <div><strong>basis:</strong>{' '}
                          {t.basis.length > 0 ? t.basis.map((eid) => (
                            <button key={eid} className="linklike small" onClick={() => focusEvidence(eid)}>
                              {eid}
                            </button>
                          )) : '—'}
                        </div>
                        {t.supporting_hypotheses.length > 0 && (
                          <div><strong>hypotheses:</strong>{' '}
                            {t.supporting_hypotheses.map((h) => (
                              <button key={h} className="linklike small" onClick={() => focusHypothesis(h)}>
                                {HYP_LABELS[h] || h}
                              </button>
                            ))}
                          </div>
                        )}
                        {t.contradictory_evidence.length > 0 && (
                          <div><strong>contradicting:</strong>{' '}
                            {t.contradictory_evidence.map((eid) => (
                              <button key={eid} className="linklike small" onClick={() => focusEvidence(eid)}>
                                {eid}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          </div>

          {/* ================= INVESTIGATION GRAPH (§16/§17) ================= */}
          <section className="panel" aria-label="Investigation graph">
            <h2>Engineering graph</h2>
            <p className="muted small">
              The provenance navigator: edges are imported analytical relationships —
              SUPPORTS is evidence-consistency (not causation), CONTRADICTS comes from
              preserved conflicts, MODELLED counterfactuals stay separate. Selecting a
              hypothesis or evidence above focuses the graph below.
            </p>
            <GraphPanel
              scopeParams={scopeParams}
              focusNode={focusNode}
              onNodeFocused={() => undefined}
              onOpenProvenance={openProvenance}
            />
          </section>

          {/* ================= COUNTERFACTUALS (§14) ================= */}
          <section className="panel" aria-label="Counterfactuals">
            <h2>Counterfactuals / sensitivity</h2>
            <table className="catalog-table">
              <thead>
                <tr>
                  <th scope="col">Candidate</th>
                  <th scope="col">Kind</th>
                  <th scope="col">State</th>
                  <th scope="col">Reason</th>
                  <th scope="col">Modelled result</th>
                </tr>
              </thead>
              <tbody>
                {result.counterfactual_candidates.map((c) => {
                  const exec = result.executed_counterfactuals.find((x) => x.candidate_id === c.candidate_id)
                  return (
                    <tr key={c.candidate_id}>
                      <td className="small"><code>{c.candidate_id.slice(0, 10)}</code></td>
                      <td className="small">{c.kind}</td>
                      <td><StateChip state={c.status} /></td>
                      <td className="muted small">{c.reason}</td>
                      <td className="small">
                        {exec ? (
                          <button
                            className="linklike"
                            onClick={() => openProvenance({
                              kind: 'COUNTERFACTUAL (MODELLED)',
                              id: exec.candidate_id.slice(0, 10),
                              provenance: {
                                source_phase: 'Counterfactual model',
                                model: exec.model,
                                baseline: exec.baseline,
                              },
                              canonicalReference: {
                                intervention: exec.intervention,
                                parameter: exec.parameter,
                              },
                              extra: [
                                { k: 'modelled delta', v: <strong className="mono">{exec.delta_s} s</strong> },
                                { k: 'validation', v: <StateChip state={exec.claim_class} /> },
                                { k: 'epistemics', v: <span className="small">{exec.epistemics}</span> },
                              ],
                              limitations: ['sensitivity is not historical effect',
                                'counterfactual is not history and not prediction'],
                            })}
                          >
                            MODELLED — NOT HISTORICAL · Δ {exec.delta_s} s
                          </button>
                        ) : '—'}
                      </td>
                    </tr>
                  )
                })}
                {result.counterfactual_candidates.length === 0 && (
                  <tr><td colSpan={5} className="muted small">
                    no counterfactual is executable under the current model scope
                  </td></tr>
                )}
              </tbody>
            </table>
            <p className="muted small">
              Counterfactuals run only when model-eligible; race-level extrapolation is
              structurally ineligible. A modelled delta is a property of the model,
              never history or prediction.
            </p>
          </section>

          {/* ================= SYNTHESIS ================= */}
          <section className="panel" aria-label="Synthesis">
            <h2>Synthesis</h2>
            <p>
              conclusion state: <StateChip state={result.synthesis.conclusion_state} />
            </p>
            <div className="split">
              <div>
                <h3 className="subhead">Established facts</h3>
                {result.synthesis.established_facts.length === 0 && <p className="muted small">none</p>}
                <ul className="small">
                  {result.synthesis.established_facts.map((f) => (
                    <li key={f.evidence_id}>
                      {f.claim} = {f.measured_value} {f.units}{' '}
                      <button className="linklike small" onClick={() => focusEvidence(f.evidence_id)}>
                        [{f.evidence_id}]
                      </button>
                    </li>
                  ))}
                </ul>
                <h3 className="subhead">Measured findings</h3>
                {result.synthesis.measured_findings.length === 0 && <p className="muted small">none</p>}
                <ul className="small">
                  {result.synthesis.measured_findings.map((f) => (
                    <li key={f.evidence_id}>
                      {f.claim} = {f.measured_value ?? '—'} {f.units}{' '}
                      <span className="muted">[{f.method}]</span>{' '}
                      <button className="linklike small" onClick={() => focusEvidence(f.evidence_id)}>
                        [{f.evidence_id}]
                      </button>
                    </li>
                  ))}
                </ul>
                <h3 className="subhead">Unresolved</h3>
                {result.synthesis.unresolved_questions.length === 0
                  ? <p className="muted small">none</p>
                  : <ul className="small">{result.synthesis.unresolved_questions.map((u, i) => <li key={i}>{u}</li>)}</ul>}
              </div>
              <div>
                <h3 className="subhead">Preserved contradictions ({result.evidence_conflicts.length})</h3>
                {result.evidence_conflicts.length === 0 && (
                  <div className="empty-state">
                    No contradiction found in the evaluated evidence — that is an
                    observation about this ledger, not a confirmation.
                  </div>
                )}
                {result.evidence_conflicts.map((c) => (
                  <div key={c.conflict_id} className="cf-intervention small">
                    <strong>{c.conflict_id}</strong> ({c.conflict_type}, {c.resolution_status}):{' '}
                    {c.description}{' '}
                    <button className="linklike small" onClick={() => focusEvidence(c.evidence_ids[1])}>
                      view contradicting evidence
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* ================= REPLAY / COMPARE / MEMORY (§18-§20) ================= */}
          <section className="panel" aria-label="Replay">
            <h2>Replay</h2>
            <ReplayPanel scopeParams={scopeParams} />
          </section>

          <section className="panel" aria-label="Comparison">
            <h2>Compare</h2>
            <ComparePanel baseScope={scopeParams} initialBLap={result.question.scope.lap_number ?? undefined} />
          </section>

          <section className="panel" aria-label="Engineering memory">
            <h2>Engineering memory</h2>
            <MemoryPanel scopeParams={scopeParams} driverA={driverA.trim()} />
          </section>
        </>
      )}

      </div>{/* /inv-main */}

      {/* ================= CONTEXTUAL INSPECTOR (side-by-side) ================= */}
      <ContextInspector
        entry={inspector}
        history={inspectorHistory}
        onBack={() => {
          const next = inspectorHistory.slice(0, -1)
          setInspectorHistory(next)
          setInspector(next[next.length - 1] ?? null)
        }}
        onClose={() => {
          setInspector(null)
          setInspectorHistory([])
        }}
        onTraceToSource={inspectorTraceToSource}
      />

    </div>
  )
}
