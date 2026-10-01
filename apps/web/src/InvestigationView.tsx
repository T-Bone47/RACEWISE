import { useCallback, useEffect, useMemo, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import {
  HYP_LABELS, QUESTION_INPUTS, QUESTION_TYPES,
} from './types'
import type { InvestigationResult } from './types'
import { StructuredError, WorkspaceSkeleton } from './workspace'
import { ClaimTag, ContextInspector, StateChip, StatePanel } from './workspace'
import type { InspectorEntry, ProvenanceTarget } from './workspace'
import { GraphPanel, ReplayPanel, ComparePanel, MemoryPanel } from './panels'
import { saveRecent } from './CommandCenterView'
import type { RecentInvestigation } from './CommandCenterView'
import { ComparabilityChip, ContextStrip, DegradationContextPanel, SpeedProfileCanvas } from './stitch'
import type { LedgerItem, ProfileSamples } from './types'
import { HYPOTHESIS_STATEMENTS, EVALUATION_RULES } from './types'

/* ============ Active Investigation — the engineering workstation ============
   Layout (mission §10): compact header (question + measured context +
   observation band) → stage rail | dominant center canvas → persistent
   bottom decision-trace strip → contextual inspector (right, on selection).

   Progressive disclosure (mission §4): the rail answers "where am I in the
   loop"; the center shows ONE stage at a time; raw provenance opens in the
   inspector. Every value still comes from the deterministic backend; the
   UI never computes conclusions.
   ========================================================================= */

/* real KPI extraction from the 6N evidence ledger (engine-generated stable
   claims; the frontend never recomputes an engineering quantity) */
function observedDeltaItem(ledger: LedgerItem[]): LedgerItem | null {
  return ledger.find((it) =>
    it.state === 'OBSERVED' &&
    typeof it.measured_value === 'number' &&
    (it.claim.startsWith('observed lap delta') ||
     it.claim.startsWith('official classified time difference') ||
     it.claim.startsWith('analytical cumulative comparable gap'))) ?? null
}

function residualItem(ledger: LedgerItem[]): LedgerItem | null {
  return ledger.find((it) => it.claim.startsWith('unexplained residual component')) ?? null
}

/* telemetry window mirror of /api/catalog/telemetry-comparison */
interface TelemetryWindow {
  t_start_s: number
  speed_delta_kmh: number
  throttle_delta_pct: number
  brake_delta_frac: number
  est_time_loss_s: number
}

interface TelemetryComparisonLite {
  verdict?: string
  reason?: string
  window_s?: number
  top_windows?: TelemetryWindow[]
}

/* §12 signature interaction: the aligned-speed instrument + per-window
   deltas for the same canonical scope. The canvas renders the REAL aligned
   profiles (opt-in samples, 0.25 s grid) with the engine's loss windows as
   linked time-axis regions — hovering a window row highlights its region.
   Never a synthetic series. */
function TelemetryDeltaPanel({
  season, round, driverA, driverB, lapNumber, sessionType,
  active, onHover,
}: {
  season: number
  round: number
  driverA: string
  driverB: string
  lapNumber: number
  sessionType: string
  active: boolean
  onHover: (hovering: boolean) => void
}) {
  const [windows, setWindows] = useState<TelemetryWindow[] | null>(null)
  const [payload, setPayload] = useState<TelemetryComparisonLite | null>(null)
  const [verdict, setVerdict] = useState<string | null>(null)
  const [reason, setReason] = useState<string | null>(null)
  const [samples, setSamples] = useState<ProfileSamples | null>(null)
  const [samplesNote, setSamplesNote] = useState<string | null>(null)
  const [hoverWindow, setHoverWindow] = useState<number | null>(null)

  const raceScoped = sessionType === 'RACE'

  useEffect(() => {
    if (!active || !raceScoped) return
    let cancelled = false
    setWindows(null)
    setPayload(null)
    setVerdict(null)
    setReason(null)
    setSamples(null)
    setSamplesNote(null)
    const params = new URLSearchParams({ driver_a: driverA, driver_b: driverB })
    if (lapNumber >= 1) params.set('lap', String(lapNumber))
    fetch(`/api/catalog/telemetry-comparison/${season}/${round}?${params}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((j: TelemetryComparisonLite) => {
        if (cancelled) return
        setPayload(j)
        setVerdict(j.verdict || null)
        setReason(j.reason || null)
        setWindows(j.top_windows || [])
      })
      .catch(() => { if (!cancelled) setVerdict('UNAVAILABLE') })
    return () => { cancelled = true }
  }, [active, raceScoped, season, round, driverA, driverB, lapNumber])

  /* real aligned speed traces: identity fraction (f=0) returns the measured
     target + reference profiles on the shared grid - the intervention is
     provably the identity, so nothing modelled is displayed here */
  useEffect(() => {
    if (!active || !raceScoped) return
    let cancelled = false
    setSamples(null)
    const params = new URLSearchParams({
      driver: driverB,
      reference_driver: driverA,
      fraction: '0',
      include_profile: 'true',
    })
    if (lapNumber >= 1) params.set('lap', String(lapNumber))
    fetch(`/api/catalog/counterfactual/${season}/${round}?${params}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((j: { status?: string; reason?: string; profile_samples?: ProfileSamples }) => {
        if (cancelled) return
        if (j.status === 'VALID' && j.profile_samples) setSamples(j.profile_samples)
        else setSamplesNote(j.status && j.status !== 'VALID'
          ? `${j.status}${j.reason ? ` — ${j.reason}` : ''}`
          : null)
      })
      .catch(() => { if (!cancelled) setSamplesNote('UNAVAILABLE') })
    return () => { cancelled = true }
  }, [active, raceScoped, season, round, driverA, driverB, lapNumber])

  if (!active) return null
  const maxLoss = windows?.length ? Math.max(...windows.map((w) => Math.abs(w.est_time_loss_s))) : 0
  const winLen = payload?.window_s ?? 5

  return (
    <section
      className="panel stage-panel"
      aria-label="Telemetry canvas and deltas"
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
    >
      <h2>Speed — {driverB} (target) vs {driverA} (reference){lapNumber >= 1 ? `, lap ${lapNumber}` : ''}</h2>
      {!raceScoped ? (
        <StatePanel
          kind="unavailable"
          title="Aligned speed profiles are computed for RACE sessions only"
          reason={`This scope is ${sessionType}. The bounded telemetry policy provides aligned lap profiles for RACE sessions; no race telemetry is substituted for a ${sessionType.toLowerCase()} question.`}
          available={['lap facts', 'timing data', 'session context']}
          missing={['aligned telemetry (RACE-scoped instrument)']}
        />
      ) : (
        <>
          <SpeedProfileCanvas
            samples={samples}
            targetLabel={`${driverB} (target)`}
            referenceLabel={`${driverA} (reference)`}
            emptyReason={samplesNote || 'speed profiles unavailable for this scope'}
            regions={(windows ?? []).map((w, i) => ({
              id: String(i),
              t_start: w.t_start_s,
              t_end: w.t_start_s + winLen,
              highlight: hoverWindow === i,
            }))}
            caption={
              <>
                Measured traces of both drivers on the shared lap-relative grid
                (shaded = the reference was faster; banded spans = the engine's
                estimated-loss windows). Native provider samples (~0.16–0.40 s
                apart) are resampled onto the 0.25 s analysis grid — this is
                aligned telemetry, not a higher native rate. Drag to inspect a
                region; double-click resets.
              </>
            }
          />
          {verdict === 'PASS' && windows && windows.length > 0 && (
            <table className="catalog-table">
              <thead>
                <tr>
                  <th scope="col">Window start [s]</th>
                  <th scope="col">Speed Δ [km/h]</th>
                  <th scope="col">Throttle Δ [%]</th>
                  <th scope="col">Brake Δ</th>
                  <th scope="col">Est. loss [s]</th>
                </tr>
              </thead>
              <tbody>
                {windows.map((w, i) => (
                  <tr
                    key={w.t_start_s}
                    className={`clickable ${hoverWindow === i ? 'selected' : ''}`}
                    onMouseEnter={() => setHoverWindow(i)}
                    onMouseLeave={() => setHoverWindow(null)}
                  >
                    <td className="mono small">{w.t_start_s}</td>
                    <td className="mono small">{w.speed_delta_kmh}</td>
                    <td className="mono small">{w.throttle_delta_pct}</td>
                    <td className="mono small">{w.brake_delta_frac}</td>
                    <td>
                      <span className="mono small">{w.est_time_loss_s}</span>
                      {maxLoss > 0 && (
                        <div className="tv-bar" style={{ width: `${(Math.abs(w.est_time_loss_s) / maxLoss) * 100}%` }} />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {verdict && verdict !== 'PASS' && (
            <StatePanel
              kind={verdict === 'INSUFFICIENT_EVIDENCE' ? 'insufficient' : 'unavailable'}
              title={`${verdict}${reason ? ` — ${reason}` : ''}`}
              reason="The comparison engine reported this state for the exact scope; nothing is broadened or interpolated to fill the gap."
            />
          )}
          <p className="muted small">
            Deterministic per-window comparison for this canonical scope
            (lap {lapNumber >= 1 ? lapNumber : 'selected by the engine'}). The UI
            renders the engine's windows — it never computes losses itself.
          </p>
        </>
      )}
    </section>
  )
}

/* the workstation stages — lifecycle-true names over the real 6N payload */
type StageId =
  | 'observation' | 'hypotheses' | 'evidence' | 'falsification'
  | 'counterfactual' | 'synthesis' | 'verification'

const STAGES: Array<{ id: StageId; label: string }> = [
  { id: 'observation', label: 'Observation' },
  { id: 'hypotheses', label: 'Hypotheses' },
  { id: 'evidence', label: 'Evidence' },
  { id: 'falsification', label: 'Falsification' },
  { id: 'counterfactual', label: 'Counterfactual' },
  { id: 'synthesis', label: 'Synthesis' },
  { id: 'verification', label: 'Verification' },
]

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

  /* workstation state */
  const [stage, setStage] = useState<StageId>('observation')
  const [hypFilter, setHypFilter] = useState('')
  const [focusNode, setFocusNode] = useState<{ type: string; key: string } | null>(null)
  const [openTrace, setOpenTrace] = useState<string | null>(null)
  /* contextual inspector state: single side-by-side surface with a back stack
     (evidence → trace-to-source → BACK returns to the evidence) */
  const [inspector, setInspector] = useState<InspectorEntry | null>(null)
  const [inspectorHistory, setInspectorHistory] = useState<InspectorEntry[]>([])
  /* §12 telemetry ↔ evidence cross-highlight state */
  const [telemetryHover, setTelemetryHover] = useState(false)
  const [copied, setCopied] = useState(false)

  function pushInspector(next: InspectorEntry) {
    setInspectorHistory((h) => {
      const top = h[h.length - 1]
      if (top && (
        (top.kind === 'evidence' && next.kind === 'evidence' && top.item.evidence_id === next.item.evidence_id) ||
        (top.kind === 'provenance' && next.kind === 'provenance' && top.target.id === next.target.id)
      )) return h
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
    setStage('observation')
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
        hypothesis_states: Object.fromEntries(
          Object.values(j.hypothesis_evaluations).map((h) => [h.hypothesis_id, h.aggregate_state]),
        ),
        observed_delta_s: typeof observedDeltaItem(j.evidence_ledger)?.measured_value === 'number'
          ? (observedDeltaItem(j.evidence_ledger)!.measured_value as number)
          : null,
        residual_s: typeof residualItem(j.evidence_ledger)?.measured_value === 'number'
          ? (residualItem(j.evidence_ledger)!.measured_value as number)
          : null,
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

  /* hypothesis drawer entry: the scientific test, disclosed (§13) */
  function openHypothesisDrawer(hypId: string) {
    const h = result?.hypothesis_evaluations[hypId]
    if (!h) return
    const byId = (ids: string[]) =>
      ids.map((id) => result?.evidence_ledger.find((x) => x.evidence_id === id))
        .filter((it): it is LedgerItem => it != null)
    focusHypothesis(hypId)
    pushInspector({
      kind: 'hypothesis',
      hyp: {
        hypothesis_id: hypId,
        label: HYP_LABELS[hypId] ?? hypId,
        statement: HYPOTHESIS_STATEMENTS[hypId] ?? hypId,
        criterion: {
          required: EVALUATION_RULES[hypId]?.required ?? '—',
          rule: EVALUATION_RULES[hypId]?.rule ?? '—',
        },
        aggregate_state: h.aggregate_state,
        falsification_status: h.falsification_status,
        supporting: byId(h.supporting_evidence),
        contradicting: byId(h.contradicting_evidence),
        non_decisive: byId(h.non_decisive_evidence),
        limitations: result?.epistemic_boundaries ?? [],
      },
    })
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

  /* stage rail status — derived only from real payload content */
  const stageStatus = (id: StageId): string => {
    if (!result) return ''
    switch (id) {
      case 'observation': {
        const gap = observedDeltaItem(result.evidence_ledger)
        return gap != null && typeof gap.measured_value === 'number'
          ? `Δ ${gap.measured_value} s`
          : 'no measured delta'
      }
      case 'hypotheses':
        return `${Object.keys(result.hypothesis_evaluations).length} evaluated`
      case 'evidence':
        return `${result.evidence_ledger.length} items · ${result.evidence_conflicts.length} conflicts`
      case 'falsification':
        return result.falsification_gate.any_unresolved_contradictions
          ? 'contradictions preserved'
          : 'no contradiction found'
      case 'counterfactual':
        return result.counterfactual_candidates.length === 0
          ? 'none eligible'
          : `${result.executed_counterfactuals.length} of ${result.counterfactual_candidates.length} executed`
      case 'synthesis':
        return result.synthesis.conclusion_state.replace(/_/g, ' ').toLowerCase()
      case 'verification':
        return 'graph · replay · memory'
    }
  }

  const stageDotClass = (id: StageId): string => {
    if (!result) return ''
    switch (id) {
      case 'falsification':
        return result.falsification_gate.any_unresolved_contradictions ? 'st-contradicted' : 'st-supported'
      case 'synthesis':
        return result.synthesis.conclusion_state === 'SUPPORTED_BY_AVAILABLE_EVIDENCE'
          ? 'st-supported'
          : result.synthesis.conclusion_state === 'MIXED_EVIDENCE' ? 'st-mixed' : 'st-insufficient'
      case 'counterfactual':
        return result.executed_counterfactuals.length > 0 ? 'st-modelled' : 'st-untestable'
      default:
        return ''
    }
  }

  const onStageKeyDown = (e: ReactKeyboardEvent, index: number) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      const next = e.key === 'ArrowDown'
        ? Math.min(index + 1, STAGES.length - 1)
        : Math.max(index - 1, 0)
      setStage(STAGES[next].id)
      const btn = document.getElementById(`stage-btn-${STAGES[next].id}`)
      btn?.focus()
    }
  }

  return (
    <div className={inspector ? 'inv-layout with-inspector' : 'inv-layout'}>
      <div className="inv-main">
      {/* ================= WORKSTATION HEADER ================= */}
      <div className="inv-hero">
        <h2 className="inv-question" aria-label="Investigation question">
          {questionType.replace(/_/g, ' ').toLowerCase()} —{' '}
          <span className="q-em">{driverA.trim() || 'driver A'}</span>
          {' '}vs{' '}
          <span className="q-em">{driverB.trim() || 'driver B'}</span>
          {' '}· {season} R{round}
          {inputs.includes('lap_number') && lapNumber >= 1 ? ` · lap ${lapNumber}` : ''}
          {inputs.includes('stint_number') && stintNumber >= 1 ? ` · stint ${stintNumber}` : ''}
          {sessionType === 'QUALIFYING' ? ' · qualifying' : ''}
        </h2>
        <div className="inv-actions">
          {result && (
            <button
              onClick={() => {
                /* clipboard API with execCommand fallback — feedback reflects
                   the real copy outcome, never a fake success */
                const id = result.investigation_id
                const done = () => {
                  setCopied(true)
                  window.setTimeout(() => setCopied(false), 1600)
                }
                const fallback = () => {
                  try {
                    const ta = document.createElement('textarea')
                    ta.value = id
                    ta.style.position = 'fixed'
                    ta.style.opacity = '0'
                    document.body.appendChild(ta)
                    ta.select()
                    if (document.execCommand('copy')) done()
                    document.body.removeChild(ta)
                  } catch { /* genuinely unavailable — no false feedback */ }
                }
                if (navigator.clipboard?.writeText) {
                  navigator.clipboard.writeText(id).then(done).catch(fallback)
                } else fallback()
              }}
              title="Copy the canonical investigation id"
            >
              {copied ? 'Copied ✓' : 'Copy ID'}
            </button>
          )}
          {result && (
            <button
              onClick={() => {
                /* export the REAL engine response verbatim — no display-only data */
                const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
                const url = URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url
                a.download = `racewise-investigation-${result.investigation_id}.json`
                a.click()
                URL.revokeObjectURL(url)
              }}
            >
              Export
            </button>
          )}
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

        {/* measured context strip — real compounds, tyre life, positions,
            weather and coverage from the canonical rows (no fabrication) */}
        <ContextStrip
          season={season}
          round={round}
          sessionType={sessionType}
          driverA={driverA.trim()}
          driverB={driverB.trim()}
          lap={inputs.includes('lap_number') && lapNumber >= 1 ? lapNumber : null}
          stint={inputs.includes('stint_number') && stintNumber >= 1 ? stintNumber : null}
        />

        {/* observation band — only values that exist in the real result */}
        {result && (
          <div className="metric-strip" role="list" aria-label="Investigation metrics">
            {(() => {
              const gap = observedDeltaItem(result.evidence_ledger)
              return gap != null && typeof gap.measured_value === 'number' ? (
                <div role="listitem">
                  <span className="m-label">Observed delta ({gap.units ?? 's'})</span>
                  <span className="m-value">{gap.measured_value}</span>
                  <span className="m-sub">
                    {gap.claim.includes('classified') ? 'official classification' : 'measured'} · {gap.evidence_id}
                  </span>
                </div>
              ) : null
            })()}
            <div role="listitem">
              <span className="m-label">Evidence items</span>
              <span className="m-value">{result.evidence_ledger.length}</span>
              <span className="m-sub">{result.evidence_ledger.filter((it) => it.state != null).length} evaluated</span>
            </div>
            <div role="listitem">
              <span className="m-label">Hypotheses tested</span>
              <span className="m-value">{Object.keys(result.hypothesis_evaluations).length}</span>
              <span className="m-sub">deterministic states</span>
            </div>
            <div role="listitem">
              <span className="m-label">Preserved contradictions</span>
              <span className="m-value">{result.evidence_conflicts.length}</span>
              <span className="m-sub">never resolved away</span>
            </div>
            <ComparabilityChip
              season={result.question.scope.season}
              round={result.question.scope.round}
              driverA={result.question.scope.driver_a}
              driverB={result.question.scope.driver_b}
              lap={result.question.scope.lap_number}
              sessionType={result.question.scope.session_type}
            />
            {(() => {
              const res = residualItem(result.evidence_ledger)
              return res != null && typeof res.measured_value === 'number' ? (
                <div role="listitem">
                  <span className="m-label">Unassigned residual</span>
                  <span className="m-value">{res.measured_value} {res.units ?? 's'}</span>
                  <span className="m-sub">UNRESOLVED — never assigned to a mechanism</span>
                </div>
              ) : null
            })()}
            <div role="listitem">
              <span className="m-label">Counterfactuals</span>
              <span className="m-value">{result.executed_counterfactuals.length}</span>
              <span className="m-sub">modelled, not historical</span>
            </div>
            <div role="listitem">
              <span className="m-label">State</span>
              <StateChip state={result.synthesis.conclusion_state} />
              <span className="m-sub">{result.synthesis.unresolved_questions.length} unresolved</span>
            </div>
          </div>
        )}

        {/* run meta — single source of truth line */}
        {result && (
          <div className="inv-meta">
            <span className="mono">{result.investigation_id}</span>
            <span title={`output hash ${result.output_hash}`}>hash <code>{result.output_hash.slice(0, 10)}</code></span>
            <span>{result.provenance.provider} · {result.provenance.analytical_chain.join(' → ')}</span>
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
              provenance
            </button>
          </div>
        )}
      </div>

      {/* scope controls — one instance, real params, honest validation */}
      <div className="controls inv-controls">
        <label>
          question type{' '}
          <select value={questionType} onChange={(e) => setQuestionType(e.target.value)}>
            {QUESTION_TYPES.map((q) => <option key={q} value={q}>{q}</option>)}
          </select>
        </label>
        <label>
          season{' '}
          <input type="number" min={1950} max={2100} value={season} style={{ width: 76 }}
                 onChange={(e) => setSeason(Number(e.target.value))} />
        </label>
        <label>
          round{' '}
          <input type="number" min={1} max={99} value={round} style={{ width: 56 }}
                 onChange={(e) => setRound(Number(e.target.value))} />
        </label>
        <label>
          session{' '}
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
          target driver{' '}
          <input type="text" value={driverA} style={{ width: 140 }}
                 onChange={(e) => setDriverA(e.target.value)} />
        </label>
        <label>
          reference driver{' '}
          <input type="text" value={driverB} style={{ width: 140 }}
                 onChange={(e) => setDriverB(e.target.value)} />
        </label>
        {inputs.includes('lap_number') && (
          <label>
            lap{' '}
            <input type="number" min={1} value={lapNumber} style={{ width: 56 }}
                   onChange={(e) => setLapNumber(Number(e.target.value))} />
          </label>
        )}
        {inputs.includes('stint_number') && (
          <label>
            stint{' '}
            <input type="number" min={1} value={stintNumber} style={{ width: 56 }}
                   onChange={(e) => setStintNumber(Number(e.target.value))} />
          </label>
        )}
        {inputs.includes('pattern_id') && (
          <label>
            pattern id{' '}
            <input type="text" value={patternId} style={{ minWidth: 200 }}
                   onChange={(e) => setPatternId(e.target.value)} />
          </label>
        )}
        <span className="muted small">
          scope data is checked at run time — UNAVAILABLE is reported, never broadened
        </span>
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
        <StatePanel
          kind="empty"
          title="No investigation loaded"
          reason="Choose a question type and scope above, or start from the command center. Every conclusion here will be bound to evidence with a decision trace."
        />
      )}

      {result && (
        <div className="inv-workstation">
          {/* ================= STAGE RAIL (left) ================= */}
          <nav className="stage-rail" aria-label="Investigation stages">
            {STAGES.map((s, i) => (
              <button
                key={s.id}
                id={`stage-btn-${s.id}`}
                className={`stage-btn ${stage === s.id ? 'active' : ''}`}
                onClick={() => setStage(s.id)}
                onKeyDown={(e) => onStageKeyDown(e, i)}
                aria-current={stage === s.id ? 'step' : undefined}
              >
                <span className={`stage-dot ${stageDotClass(s.id)}`} aria-hidden="true" />
                <span className="stage-name">{s.label}</span>
                <span className="stage-status mono">{stageStatus(s.id)}</span>
              </button>
            ))}
            <div className="stage-rail-foot">
              <button
                className="linklike small"
                onClick={() => {
                  const p = new URLSearchParams({
                    question_type: 'HYPOTHESIS_EVALUATION',
                    driver_a: result.question.scope.driver_a,
                    driver_b: result.question.scope.driver_b,
                    season: String(result.question.scope.season),
                    round: String(result.question.scope.round),
                    session_type: result.question.scope.session_type,
                  })
                  if (result.question.scope.lap_number != null) p.set('lap_number', String(result.question.scope.lap_number))
                  window.location.hash = `#/falsification?${p.toString()}`
                  window.dispatchEvent(new HashChangeEvent('hashchange'))
                }}
              >
                Open falsification matrix →
              </button>
            </div>
          </nav>

          {/* ================= CENTER — dominant analytical canvas ================= */}
          <div className="stage-center">
            {/* ---------- OBSERVATION ---------- */}
            {stage === 'observation' && (
              <>
                <TelemetryDeltaPanel
                  season={result.question.scope.season}
                  round={result.question.scope.round}
                  driverA={result.question.scope.driver_a}
                  driverB={result.question.scope.driver_b}
                  lapNumber={result.question.scope.lap_number ?? 0}
                  sessionType={result.question.scope.session_type}
                  active={result.evidence_ledger.some((it) =>
                    it.source_tool.includes('telemetry') ||
                    it.source_phase === '6E' ||
                    it.source_phase === '6F')}
                  onHover={setTelemetryHover}
                />
                {result.question.scope.session_type === 'RACE' && (
                  <DegradationContextPanel
                    season={result.question.scope.season}
                    round={result.question.scope.round}
                    driverA={result.question.scope.driver_a}
                    driverB={result.question.scope.driver_b}
                    stint={result.question.scope.stint_number}
                  />
                )}
              </>
            )}

            {/* ---------- HYPOTHESES ---------- */}
            {stage === 'hypotheses' && (
              <section className="panel stage-panel" aria-label="Hypothesis matrix">
                <h2>Hypothesis matrix (never ranked)</h2>
                <div className="hyp-rows">
                  {Object.values(result.hypothesis_evaluations).map((h) => (
                    <button
                      key={h.hypothesis_id}
                      className="hyp-row"
                      onClick={() => openHypothesisDrawer(h.hypothesis_id)}
                      title="Open the scientific test in the inspector"
                    >
                      <span className={`ef-badge ${hypStateClass(h.aggregate_state)}`}>
                        {HYP_LABELS[h.hypothesis_id]?.split(' ')[0] ?? h.hypothesis_id}
                      </span>
                      <span className="hyp-row-name">{HYP_LABELS[h.hypothesis_id] ?? h.hypothesis_id}</span>
                      <span className="hyp-row-counts mono">
                        <span className="hc-sup" title="supporting evidence">{h.evidence_coverage.supporting}+</span>
                        <span className="hc-con" title="contradicting evidence">{h.evidence_coverage.contradicting}−</span>
                        <span className="hc-neu" title="non-decisive evidence">{h.evidence_coverage.non_decisive}~</span>
                      </span>
                      <StateChip state={h.aggregate_state} />
                    </button>
                  ))}
                </div>
                <p className="muted small">
                  Click a hypothesis to open its test in the inspector: prediction, evaluated
                  evidence, falsification criterion and result. {result.falsification_gate.rule}
                </p>
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
            )}

            {/* ---------- EVIDENCE ---------- */}
            {stage === 'evidence' && (
              <section className="panel stage-panel" aria-label="Evidence ledger">
                <h2>Evidence ledger ({filteredLedger.length}/{ledger.length})</h2>
                <div className="controls">
                  <label>
                    hypothesis{' '}
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
                      <th scope="col">Claim</th>
                      <th scope="col">Effect</th>
                      <th scope="col">State</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredLedger.map((it) => (
                      <tr
                        key={it.evidence_id}
                        className={`clickable ${conflictIds.has(it.evidence_id) ? 'selected' : ''} ${
                          telemetryHover && (it.source_phase === '6E' || it.source_phase === '6F') ? 'linked' : ''
                        }`}
                        onClick={() => {
                          pushInspector({ kind: 'evidence', item: it })
                          focusEvidence(it.evidence_id)
                        }}
                      >
                        <td className="small"><code>{it.evidence_id}</code></td>
                        <td className="small"><ClaimTag claimClass={it.claim_class} />{it.evidence_type}</td>
                        <td className="small">
                          {it.claim}
                          {it.measured_value != null && (
                            <span className="muted"> = {typeof it.measured_value === 'number' ? it.measured_value : '…'} {it.units ?? ''}</span>
                          )}
                        </td>
                        <td className="small mono ev-effect">
                          {it.contradicts
                            ? <span className="hc-con" title="contradicts">↮ {it.hypothesis_ids.map((h) => h.split('_')[0]).join(' ')}</span>
                            : it.supports
                              ? <span className="hc-sup" title="supports">→ {it.hypothesis_ids.map((h) => h.split('_')[0]).join(' ')}</span>
                              : <span className="hc-neu" title="no decisive hypothesis relation">—</span>}
                          <span className="muted small"> {it.source_phase}</span>
                        </td>
                        <td><StateChip state={it.state} /></td>
                      </tr>
                    ))}
                    {filteredLedger.length === 0 && (
                      <tr><td colSpan={5} className="muted small">no evidence matches this filter</td></tr>
                    )}
                  </tbody>
                </table>
                <h3 className="subhead">Preserved contradictions ({result.evidence_conflicts.length})</h3>
                {result.evidence_conflicts.length === 0 && (
                  <p className="muted small">
                    No contradiction found in the evaluated evidence — that is an
                    observation about this ledger, not a confirmation.
                  </p>
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
              </section>
            )}

            {/* ---------- FALSIFICATION ---------- */}
            {stage === 'falsification' && (
              <section className="panel stage-panel" aria-label="Falsification">
                <h2>Falsification</h2>
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
                <p className="small">
                  gate rule: <span className="muted">{result.falsification_gate.rule}</span>
                </p>
                <p className="small">
                  establishable: {' '}
                  <span className="mono">
                    {result.falsification_gate.establishable_hypotheses.length > 0
                      ? result.falsification_gate.establishable_hypotheses.map((h) => HYP_LABELS[h] || h).join(', ')
                      : 'none'}
                  </span>
                </p>
                <p className="muted small">
                  Verdicts are evidence-consistency statements — SUPPORT is not PROOF, and
                  NOT_TESTABLE never becomes CONTRADICTED. The full prediction/criterion/verdict
                  matrix lives in its own view.
                </p>
              </section>
            )}

            {/* ---------- COUNTERFACTUAL ---------- */}
            {stage === 'counterfactual' && (
              <section className="panel stage-panel" aria-label="Counterfactuals">
                <h2>Counterfactuals / sensitivity <span className="ef-badge st-modelled">MODELLED — NOT HISTORICAL</span></h2>
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
            )}

            {/* ---------- SYNTHESIS (engineering report) ---------- */}
            {stage === 'synthesis' && (
              <section className="panel stage-panel" aria-label="Synthesis">
                <h2>Engineering conclusion — {result.synthesis.conclusion_state.replace(/_/g, ' ').toLowerCase()}</h2>
                <div className="report-grid">
                  <div className="report-block">
                    <h3 className="subhead">Observed</h3>
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
                    <h3 className="subhead">Hypothesis findings</h3>
                    <ul className="small">
                      {Object.entries(result.synthesis.hypothesis_findings).map(([id, f]) => (
                        <li key={id}>
                          <button className="linklike small" onClick={() => focusHypothesis(id)}>
                            {HYP_LABELS[id] ?? id}
                          </button>{' '}
                          <StateChip state={f.aggregate_state} />
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="report-block">
                    <h3 className="subhead">Contradictory evidence</h3>
                    {result.synthesis.contradictory_evidence.length === 0 && <p className="muted small">none</p>}
                    <ul className="small">
                      {result.synthesis.contradictory_evidence.map((c) => (
                        <li key={c.evidence_id}>
                          <button className="linklike small" onClick={() => focusEvidence(c.evidence_id)}>
                            [{c.evidence_id}]
                          </button>{' '}
                          {c.claim}
                        </li>
                      ))}
                    </ul>
                    <h3 className="subhead">Unresolved</h3>
                    {result.synthesis.unresolved_questions.length === 0
                      ? <p className="muted small">none</p>
                      : <ul className="small">{result.synthesis.unresolved_questions.map((u, i) => <li key={i}>{u}</li>)}</ul>}
                    {(() => {
                      const res = residualItem(result.evidence_ledger)
                      return res != null && typeof res.measured_value === 'number' ? (
                        <div className="residual-callout">
                          <span className="t-microlabel">Unresolved residual</span>
                          <span className="mono residual-value">{res.measured_value} {res.units ?? 's'}</span>
                          <span className="muted small">UNRESOLVED — never assigned to a mechanism</span>
                        </div>
                      ) : null
                    })()}
                    <h3 className="subhead">Counterfactual findings</h3>
                    {result.synthesis.counterfactual_findings.length === 0 && <p className="muted small">none</p>}
                    <ul className="small">
                      {result.synthesis.counterfactual_findings.map((f) => (
                        <li key={f.candidate_id}>
                          {f.kind} · Δ {f.delta_s ?? '—'} s · <StateChip state={f.claim_class} />
                        </li>
                      ))}
                    </ul>
                    <h3 className="subhead">Limitations</h3>
                    <ul className="small muted">
                      {result.synthesis.limitations.map((l, i) => <li key={i}>{l}</li>)}
                    </ul>
                  </div>
                </div>
                {/* synthesis actions — every button maps to a real capability */}
                <div className="synth-actions" aria-label="Synthesis actions">
                  <button
                    onClick={() => {
                      const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
                      const url = URL.createObjectURL(blob)
                      const a = document.createElement('a')
                      a.href = url
                      a.download = `racewise-investigation-${result.investigation_id}.json`
                      a.click()
                      URL.revokeObjectURL(url)
                    }}
                  >
                    Export investigation (JSON)
                  </button>
                  <button
                    onClick={() => { setStage('verification'); document.getElementById('inv-replay')?.scrollIntoView({ block: 'start' }) }}
                  >
                    Replay (deterministic re-run)
                  </button>
                  {result.question.scope.session_type === 'RACE' && (
                    <button
                      onClick={() => {
                        const p = new URLSearchParams({
                          season: String(result.question.scope.season),
                          round: String(result.question.scope.round),
                          driver: result.question.scope.driver_b,
                          reference: result.question.scope.driver_a,
                        })
                        if (result.question.scope.lap_number != null) p.set('lap', String(result.question.scope.lap_number))
                        window.location.hash = `#/counterfactual?${p.toString()}`
                        window.dispatchEvent(new HashChangeEvent('hashchange'))
                      }}
                    >
                      Open counterfactual lab with this scope
                    </button>
                  )}
                </div>
              </section>
            )}

            {/* ---------- VERIFICATION ---------- */}
            {stage === 'verification' && (
              <>
                <section className="panel stage-panel" aria-label="Investigation graph">
                  <h2>Engineering graph</h2>
                  <p className="muted small">
                    The provenance navigator: edges are imported analytical relationships —
                    SUPPORTS is evidence-consistency (not causation), CONTRADICTS comes from
                    preserved conflicts, MODELLED counterfactuals stay separate. Selecting a
                    hypothesis or evidence above focuses the graph.
                  </p>
                  <GraphPanel
                    scopeParams={scopeParams}
                    focusNode={focusNode}
                    onNodeFocused={() => undefined}
                    onOpenProvenance={openProvenance}
                  />
                </section>
                <section className="panel stage-panel" id="inv-replay" aria-label="Replay">
                  <h2>Replay</h2>
                  <ReplayPanel scopeParams={scopeParams} />
                </section>
                <section className="panel stage-panel" aria-label="Comparison">
                  <h2>Compare</h2>
                  <ComparePanel baseScope={scopeParams} initialBLap={result.question.scope.lap_number ?? undefined} />
                </section>
                <section className="panel stage-panel" aria-label="Engineering memory">
                  <h2>Engineering memory</h2>
                  <MemoryPanel scopeParams={scopeParams} driverA={driverA.trim()} />
                </section>
              </>
            )}

            {/* ================= PERSISTENT DECISION TRACE (bottom) ================= */}
            <section className="trace-strip-wrap" aria-label="Decision trace">
              <div className="trace-strip-head">
                <span className="t-microlabel">Decision trace ({result.decision_trace.length})</span>
                <span className="muted small">click a step for its basis</span>
              </div>
              <div className="trace-strip" role="tablist" aria-label="Decision trace steps">
                {result.decision_trace.map((t) => (
                  <button
                    key={t.trace_id}
                    role="tab"
                    aria-selected={openTrace === t.trace_id}
                    className={`trace-node ${openTrace === t.trace_id ? 'active' : ''}`}
                    onClick={() => setOpenTrace(openTrace === t.trace_id ? null : t.trace_id)}
                  >
                    <span className={`trace-dot ${stateChipClassSafe(t.status)}`} aria-hidden="true" />
                    <span className="mono">{t.trace_id}</span>
                  </button>
                ))}
              </div>
              {openTrace && (() => {
                const t = result.decision_trace.find((x) => x.trace_id === openTrace)
                if (!t) return null
                return (
                  <div className="trace-detail">
                    <div className="trace-detail-head">
                      <span className="mono">{t.trace_id}</span>
                      <StateChip state={t.status} />
                      <span className="muted small">{t.type}</span>
                    </div>
                    <p className="small">{t.statement}</p>
                    <div className="muted small">
                      basis: {t.basis.length > 0 ? t.basis.map((eid) => (
                        <button key={eid} className="linklike small mono" onClick={() => focusEvidence(eid)}>
                          {eid}
                        </button>
                      )) : '—'}
                    </div>
                    {t.supporting_hypotheses.length > 0 && (
                      <div className="muted small">
                        hypotheses: {t.supporting_hypotheses.map((h) => (
                          <button key={h} className="linklike small" onClick={() => focusHypothesis(h)}>
                            {HYP_LABELS[h] || h}
                          </button>
                        ))}
                      </div>
                    )}
                    {t.contradictory_evidence.length > 0 && (
                      <div className="muted small">
                        contradicting: {t.contradictory_evidence.map((eid) => (
                          <button key={eid} className="linklike small mono" onClick={() => focusEvidence(eid)}>
                            {eid}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })()}
            </section>
          </div>
        </div>
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
        onOpenEvidence={(item) => pushInspector({ kind: 'evidence', item })}
      />

    </div>
  )
}

/* hypothesis-row state class without importing stateChipClass's default */
function hypStateClass(state: string): string {
  switch (state) {
    case 'SUPPORTED':
    case 'SUPPORTED_BY_AVAILABLE_EVIDENCE':
      return 'st-supported'
    case 'PARTIALLY_SUPPORTED':
      return 'st-partial'
    case 'CONTRADICTED':
      return 'st-contradicted'
    case 'MIXED_EVIDENCE':
      return 'st-mixed'
    case 'INSUFFICIENT_EVIDENCE':
      return 'st-insufficient'
    default:
      return 'st-untestable'
  }
}

function stateChipClassSafe(state: string | null | undefined): string {
  if (!state) return 'st-untestable'
  switch (state) {
    case 'SUPPORTED':
    case 'OBSERVED':
    case 'ESTABLISHED':
      return 'st-supported'
    case 'CONTRADICTED':
      return 'st-contradicted'
    case 'MIXED_EVIDENCE':
    case 'UNRESOLVED':
      return 'st-mixed'
    case 'MODELLED':
      return 'st-modelled'
    default:
      return 'st-untestable'
  }
}
