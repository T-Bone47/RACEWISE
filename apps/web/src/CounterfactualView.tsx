import { useCallback, useEffect, useMemo, useState } from 'react'
import type { EnvelopeSensitivity, ProfileSamples, ScenarioPoint } from './types'
import { SpeedProfileCanvas } from './stitch'
import { modelLayerKey } from './motion'
import { StateChip } from './workspace'

/* ============ Stitch Counterfactual Lab — the real 6I/6J engine ============
   Every number is the engine's own output: modelled lap times, deltas,
   validation gates, profile samples (opt-in) and the Phase 6J scenario
   sweep. Everything modelled is labelled MODELLED — NOT HISTORICAL. No
   solver branding, no thread counts, no aero notes: only the real method.
   ========================================================================== */

interface Gate {
  status: string
  detail: string
}

interface CounterfactualResult {
  analysis?: string
  version?: string
  status: string
  reason?: string
  season?: number
  round?: number
  session_type?: string
  driver?: string
  reference_driver?: string | null
  lap_number?: number
  signal?: string
  intervention?: { type: string; fraction: number }
  epistemics?: string
  validation_gates?: Record<string, Gate>
  profile_summary?: {
    signal: string
    unit: string
    n_points: number
    grid_step_s: number
    coverage_s: number
    target_mean_speed_kmh: number
    target_max_speed_kmh: number
    transformed_mean_speed_kmh: number
    reference_mean_speed_kmh: number | null
  }
  profile_samples?: ProfileSamples
  intervention_definition?: string
  model?: {
    method: string
    segment_s: number
    n_segments: number
    units: string
    baseline_reproduction?: {
      model_baseline_s: number
      measured_grid_duration_s: number
      error_s: number
      identity_intervention_delta_s: number
    }
  }
  baseline_result?: { modeled_lap_time_s: number }
  counterfactual_result?: { modeled_lap_time_s: number }
  counterfactual_delta_s?: number
  deficit_closed_s?: number
  delta_sign_convention?: string
  cross_check_6e?: { note?: string; attribution_status?: string; attribution_estimated_pace_component_s?: number | null } | null
  assumptions?: string[]
  limitations?: string[]
  provenance?: { tables?: string[]; provider?: string; counterfactual_version?: string; alignment?: string }
  output_hash?: string
}

interface EnvelopeResult {
  status: string
  reason?: string
  driver?: string
  reference_driver?: string | null
  anchor_lap?: number | null
  scenario_definition?: { type: string; parameters: number[]; reference?: string | null }
  scenarios?: ScenarioPoint[]
  sensitivity?: EnvelopeSensitivity
  envelope?: { grid?: { step_s: number; coverage_s: number }; band_summary?: { mean_band_width_kmh: number } }
  model_baseline?: { baseline_time_s: number }
}

interface SessionRef { season: number; round: number; label: string }

const KNOWN_SESSIONS: Array<{ season: number; round: number }> = [
  { season: 2025, round: 1 },
  { season: 2024, round: 14 },
  { season: 2023, round: 1 },
  { season: 2022, round: 4 },
]

const GATE_OK = new Set(['PASS'])

export default function CounterfactualView({ presetParams }: { presetParams?: URLSearchParams }) {
  const [sessions, setSessions] = useState<SessionRef[]>([])
  const [selected, setSelected] = useState(() => {
    const s = presetParams?.get('season')
    const r = presetParams?.get('round')
    return s && r ? `${s}-${r}` : '2023-1'
  })
  const [driver, setDriver] = useState(() => presetParams?.get('driver') || '')
  const [reference, setReference] = useState(() => presetParams?.get('reference') || '')
  const [lapInput, setLapInput] = useState(() => {
    const l = presetParams?.get('lap')
    return l ? String(l) : ''
  })
  const [fraction, setFraction] = useState(0.5)
  const [result, setResult] = useState<CounterfactualResult | null>(null)
  const [envelope, setEnvelope] = useState<EnvelopeResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      try {
        const resp = await fetch('/api/catalog/sessions?capability=telemetry&page_size=100')
        if (!resp.ok) return
        const data = await resp.json()
        const refs: SessionRef[] = (data.sessions || []).map(
          (s: { season: number; round: number; race_name: string | null }) => ({
            season: s.season,
            round: s.round,
            label: s.race_name || `${s.season} R${s.round}`,
          }),
        )
        if (refs.length > 0) {
          setSessions(refs)
        }
      } catch {
        /* fallback list below */
      }
    }
    load()
  }, [])

  const run = useCallback(async () => {
    setLoading(true)
    setError(null)
    setResult(null)
    setEnvelope(null)
    try {
      const [season, round] = selected.split('-')
      const params = new URLSearchParams({
        fraction: String(fraction),
        include_profile: 'true',
      })
      if (driver.trim()) params.set('driver', driver.trim())
      if (reference.trim()) params.set('reference_driver', reference.trim())
      const lapNum = Number(lapInput)
      if (lapInput.trim() && Number.isFinite(lapNum) && lapNum >= 1) params.set('lap', String(lapNum))
      const resp = await fetch(`/api/catalog/counterfactual/${season}/${round}?${params}`)
      if (!resp.ok) throw new Error(`Counterfactual request failed (${resp.status})`)
      const cf = (await resp.json()) as CounterfactualResult
      setResult(cf)

      /* Phase 6J sweep for the same scope — the real sensitivity surface */
      if (cf.status === 'VALID') {
        const envParams = new URLSearchParams({ scenario_type: 'DEFICIT_REDUCTION' })
        if (cf.driver) envParams.set('driver', cf.driver)
        if (cf.reference_driver) envParams.set('reference_driver', cf.reference_driver)
        const envResp = await fetch(`/api/catalog/performance-envelope/${season}/${round}?${envParams}`)
        if (envResp.ok) setEnvelope((await envResp.json()) as EnvelopeResult)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [selected, fraction, driver, reference, lapInput])

  useEffect(() => {
    /* auto-run when arriving from the investigation workspace with a scope */
    if (presetParams && (presetParams.get('season') || presetParams.get('driver'))) {
      void run()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const sessionList: SessionRef[] =
    sessions.length > 0
      ? sessions
      : KNOWN_SESSIONS.map((s) => ({ ...s, label: `${s.season} R${s.round}` }))

  const valid = result?.status === 'VALID'
  const gates = result?.validation_gates || {}
  const gatesPassed = Object.values(gates).filter((g) => GATE_OK.has(g.status)).length
  const gatesTotal = Object.keys(gates).length
  const fmt = (v: number | null | undefined, d = 3) =>
    v === null || v === undefined ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(d)} s`

  const sweepPoints = useMemo(
    () => (envelope?.scenarios ?? []).filter((s) => s.status === 'VALID' && typeof s.delta_s === 'number'),
    [envelope],
  )

  return (
    <div className="catalog cf-lab">
      {/* ============ sub-bar: scope + MODELLED badge ============ */}
      <div className="cf-subbar">
        <h2>Counterfactual Lab — validated telemetry counterfactual (modelled)</h2>
        <span className="ef-badge st-modelled" title={result?.epistemics}>
          MODELLED · NOT HISTORICAL
        </span>
      </div>
      <p className="muted small">
        Under a bounded speed-profile intervention, the deterministic fixed-distance
        lap-time model measures its own sensitivity. A counterfactual result is{' '}
        <em>not</em> a historical fact, a prediction, or a causal proof. Only speed has a
        lap-time model; throttle, brake, gear, rpm and drs interventions are reported as
        UNSUPPORTED rather than approximated.
      </p>

      {/* ============ intervention controls ============ */}
      <div className="catalog-filters">
        <label>
          session{' '}
          <select value={selected} onChange={(e) => setSelected(e.target.value)}>
            {sessionList.map((s) => (
              <option key={`${s.season}-${s.round}`} value={`${s.season}-${s.round}`}>
                {s.season} R{s.round} — {s.label}
              </option>
            ))}
          </select>
        </label>
        <label className="small">
          target driver{' '}
          <input
            type="text" value={driver} placeholder="session telemetry pair default"
            style={{ width: 150 }}
            onChange={(e) => setDriver(e.target.value)}
          />
        </label>
        <label className="small">
          reference driver{' '}
          <input
            type="text" value={reference} placeholder="session telemetry pair default"
            style={{ width: 150 }}
            onChange={(e) => setReference(e.target.value)}
          />
        </label>
        <label className="small">
          lap{' '}
          <input
            type="text" value={lapInput} placeholder="first VALID lap"
            style={{ width: 90 }}
            onChange={(e) => setLapInput(e.target.value)}
          />
        </label>
        <label className="small">
          deficit recovery fraction (REMOVE_DEFICIT){' '}
          <input
            type="number" min={0} max={1} step={0.05} value={fraction}
            style={{ width: 70 }}
            onChange={(e) => setFraction(Number(e.target.value))}
          />
        </label>
        <button className="primary" onClick={() => void run()} disabled={loading}>
          {loading ? 'Simulating…' : 'Run counterfactual'}
        </button>
      </div>

      {error && <div className="catalog-error">Error: {error}</div>}

      {result && !valid && (
        <div className="catalog-empty">
          <StateChip state={result.status} /> —{' '}
          {result.reason || 'counterfactual not possible with current evidence'}
        </div>
      )}

      {result && valid && (
        <>
          {/* ============ KPI ribbons (all real fields) ============ */}
          <div className="cf-ribbons" role="list" aria-label="Counterfactual summary">
            <div className="cf-ribbon" role="listitem">
              <span className="m-label">Lap {result.lap_number} · {result.driver} vs {result.reference_driver}</span>
              <span className="m-value">{result.intervention?.type}</span>
              <span className="m-sub">fraction {result.intervention?.fraction}</span>
            </div>
            <div className="cf-ribbon" role="listitem">
              <span className="m-label">Baseline (modelled)</span>
              <span className="m-value">{result.baseline_result?.modeled_lap_time_s.toFixed(3)} s</span>
              <span className="m-sub">
                measured grid {result.model?.baseline_reproduction?.measured_grid_duration_s} s ·
                reproduction error {result.model?.baseline_reproduction?.error_s} s
              </span>
            </div>
            <div className="cf-ribbon" role="listitem">
              <span className="m-label">Counterfactual (modelled)</span>
              <span className="m-value">{result.counterfactual_result?.modeled_lap_time_s.toFixed(3)} s</span>
              <span className="m-sub">MODELLED — NOT HISTORICAL</span>
            </div>
            <div className="cf-ribbon" role="listitem">
              <span className="m-label">Modelled delta</span>
              <span className={`m-value ${result.counterfactual_delta_s !== undefined && result.counterfactual_delta_s < 0 ? 'rg-narrowing' : 'rg-wider'}`}>
                {fmt(result.counterfactual_delta_s)}
              </span>
              <span className="m-sub">{result.delta_sign_convention}</span>
            </div>
            <div className="cf-ribbon" role="listitem">
              <span className="m-label">Deficit closed (model)</span>
              <span className="m-value">{fmt(result.deficit_closed_s)}</span>
              <span className="m-sub">within the model only</span>
            </div>
            <div className="cf-ribbon" role="listitem">
              <span className="m-label">Validation gates</span>
              <span className="m-value">{gatesPassed} / {gatesTotal} PASS</span>
              <span className="m-sub">engine-checked, never simulated client-side</span>
            </div>
          </div>

          {/* ============ intervention definition + gates ============ */}
          <div className="cf-columns">
            <section className="panel" aria-label="Intervention definition">
              <h2>Intervention</h2>
              <div className="cf-intervention">
                <strong>DEFINITION</strong>&nbsp;
                <span className="mono small">{result.intervention_definition}</span>
              </div>
              <div className="cf-intervention">
                <strong>MODEL</strong>&nbsp;
                <span className="small">{result.model?.method}</span>
                <div className="muted small mono">
                  segment {result.model?.segment_s} s · {result.model?.n_segments} segments · grid {result.profile_summary?.grid_step_s} s
                  · coverage {result.profile_summary?.coverage_s} s
                </div>
              </div>
              <h3 className="subhead">Validation gates (engine output)</h3>
              <ul className="cf-gates">
                {Object.entries(gates).map(([name, gate]) => (
                  <li key={name} className={GATE_OK.has(gate.status) ? 'rg-ok' : 'rg-warn'}>
                    <strong>{gate.status === 'PASS' ? 'PASS' : gate.status}</strong> {name}
                    {gate.detail ? <span className="muted"> — {gate.detail}</span> : null}
                  </li>
                ))}
              </ul>
            </section>

            {/* ============ aligned profile canvas (real samples) ============ */}
            <section className="panel" aria-label="Speed profiles">
              <h2>Aligned speed profiles</h2>
              <SpeedProfileCanvas
                samples={result.profile_samples ?? null}
                targetLabel={`${result.driver} (baseline)`}
                referenceLabel={`${result.reference_driver} (reference)`}
                showCounterfactual
                counterfactualLabel="counterfactual"
                modelKey={modelLayerKey(result.intervention?.fraction)}
                emptyReason="profile samples unavailable for this lap"
                caption={
                  <>
                    Baseline and reference are measured traces; the counterfactual trace
                    (dashed violet) is the MODELLED intervention — it re-fades when the
                    scenario changes while the measured traces stay fixed. All series
                    share the 0.25 s lap-relative analysis grid.
                  </>
                }
              />
            </section>
          </div>

          {/* ============ sensitivity sweep (real 6J scenarios) ============ */}
          <section className="panel" aria-label="Sensitivity sweep">
            <h2>Model sensitivity sweep — bounded scenarios</h2>
            {!envelope || envelope.status !== 'VALID' ? (
              <div className="empty-state">
                {envelope?.status ? (
                  <>{envelope.status}{envelope.reason ? ` — ${envelope.reason}` : ''} — the sweep is not rendered without valid scenario points.</>
                ) : (
                  <>Sweep unavailable for this scope.</>
                )}
              </div>
            ) : sweepPoints.length === 0 ? (
              <div className="empty-state">no valid scenario points in the sweep</div>
            ) : (
              <div className="cf-sweep">
                <table className="catalog-table">
                  <thead>
                    <tr>
                      <th scope="col">Scenario parameter</th>
                      <th scope="col">Modelled lap time [s]</th>
                      <th scope="col">Delta vs baseline [s]</th>
                      <th scope="col">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(envelope.scenarios ?? []).map((s, i) => (
                      <tr key={i} className={s.parameter === result.intervention?.fraction ? 'selected' : ''}>
                        <td className="mono small">{s.parameter}</td>
                        <td className="mono small">{s.modeled_lap_time_s != null ? s.modeled_lap_time_s.toFixed(6) : '—'}</td>
                        <td className="mono small">{s.delta_s !== undefined && s.delta_s !== null ? fmt(s.delta_s) : '—'}</td>
                        <td><StateChip state={s.status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="muted small">
                  response: <strong>{envelope.sensitivity?.response?.status}</strong>
                  {envelope.sensitivity?.response?.total_range_s !== undefined
                    ? ` · measured range ${fmt(envelope.sensitivity.response.total_range_s)}`
                    : ''}
                  {' · '}{envelope.sensitivity?.note}
                  <br />
                  anchor lap {envelope.anchor_lap ?? '—'} · median-profile model on the
                  driver's own clean laps — every delta is model sensitivity, never a
                  causal effect and never a historical result.
                </div>
              </div>
            )}
          </section>

          {/* ============ epistemics / provenance ============ */}
          <section className="panel" aria-label="Epistemics and provenance">
            <h2>Epistemics, assumptions, limitations, provenance</h2>
            <div className="rg-accounting">
              <strong>Interpretation</strong>
              <p>{result.epistemics}. The delta quantifies how strongly the lap-time model
              responds to the specified intervention — it does not establish that the
              deficit caused the historical gap, and the attribution residual applies at
              full removal.</p>
            </div>
            {result.cross_check_6e && (
              <p className="muted small">
                Lap-attribution cross-check (informational, different quantity — never merged):{' '}
                {result.cross_check_6e.note}
                {result.cross_check_6e.attribution_status
                  ? ` status ${result.cross_check_6e.attribution_status}`
                  : ''}
                {result.cross_check_6e.attribution_estimated_pace_component_s != null
                  ? `, estimated pace component ${result.cross_check_6e.attribution_estimated_pace_component_s} s`
                  : ''}.
              </p>
            )}
            <div className="split">
              <div>
                <h3 className="subhead">Assumptions</h3>
                <ul className="small">{(result.assumptions ?? []).map((a) => <li key={a}>{a}</li>)}</ul>
              </div>
              <div>
                <h3 className="subhead">Limitations</h3>
                <ul className="small">{(result.limitations ?? []).map((l) => <li key={l}>{l}</li>)}</ul>
              </div>
            </div>
            <p className="muted small mono">
              {result.provenance?.provider} · {result.provenance?.alignment} ·
              counterfactual v{result.provenance?.counterfactual_version} ·
              output hash {result.output_hash}
            </p>
            <button
              onClick={() => {
                const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
                const url = URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url
                a.download = `racewise-counterfactual-${result.output_hash}.json`
                a.click()
                URL.revokeObjectURL(url)
              }}
            >
              Export scenario (verbatim JSON)
            </button>
          </section>
        </>
      )}
    </div>
  )
}
