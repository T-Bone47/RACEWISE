import { useCallback, useEffect, useState } from 'react'

interface BandSegment {
  t_start_s: number
  t_end_s: number
  band_lower_mean_kmh: number
  band_centre_mean_kmh: number
  band_upper_mean_kmh: number
  band_width_mean_kmh: number
}

interface ScenarioPoint {
  parameter: number
  label: string
  status: string
  delta_s?: number
  modeled_lap_time_s?: number
}

interface EnvelopeResult {
  status: string
  reason?: string
  driver?: string
  reference_driver?: string | null
  anchor_lap?: number
  envelope?: {
    scope: string
    laps_used: number[]
    band_summary: {
      mean_band_width_kmh: number
      overall_min_speed_kmh: number
      overall_max_speed_kmh: number
    }
    grid: { n_points: number; step_s: number; coverage_s: number }
  }
  band_segments?: BandSegment[]
  model_baseline?: {
    baseline_time_s: number
    measured_grid_duration_s: number
    reproduction_error_s: number
  }
  scenarios?: ScenarioPoint[]
  sensitivity?: {
    response: {
      status: string
      total_range_s?: number
      max_abs_second_difference_s?: number
    }
    note: string
  }
  regional_response?: Array<{ t_start_s: number; t_end_s: number; scenario_delta_s: number }> | null
  stint_response?: {
    parameter: number
    per_lap: Array<{ lap_number: number; delta_s: number }>
    sensitivity_trend_s_per_lap: number
  } | null
  epistemics?: string
  output_hash?: string
}

interface SessionRef { season: number; round: number; label: string }

const KNOWN_SESSIONS: Array<{ season: number; round: number }> = [
  { season: 2025, round: 1 },
  { season: 2024, round: 14 },
  { season: 2023, round: 1 },
  { season: 2022, round: 4 },
]

export default function PerformanceEnvelopeView() {
  const [sessions, setSessions] = useState<SessionRef[]>([])
  const [selected, setSelected] = useState('2023-1')
  const [scenario, setScenario] = useState('DEFICIT_REDUCTION')
  const [result, setResult] = useState<EnvelopeResult | null>(null)
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
          setSelected(`${refs[0].season}-${refs[0].round}`)
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
    try {
      const [season, round] = selected.split('-')
      const resp = await fetch(`/api/catalog/performance-envelope/${season}/${round}?scenario_type=${scenario}`)
      if (!resp.ok) throw new Error(`Envelope request failed (${resp.status})`)
      setResult(await resp.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    finally {
      setLoading(false)
    }
  }, [selected, scenario])

  const sessionList: SessionRef[] =
    sessions.length > 0
      ? sessions
      : KNOWN_SESSIONS.map((s) => ({ ...s, label: `${s.season} R${s.round}` }))

  const valid = result?.status === 'VALID'
  const fmt = (v: number | null | undefined, d = 3) =>
    v === null || v === undefined ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(d)} s`

  return (
    <div className="catalog attribution-view">
      <h2>Driver Performance Envelope</h2>
      <p className="muted small">
        The <strong>measured</strong> speed band of a driver's own clean comparable laps —
        not an ideal lap, not a theoretical maximum, not a prediction. Bounded typed
        scenarios run through the validated fixed-distance lap-time model; every delta
        is model sensitivity under a specified intervention, never causality.
      </p>

      <div className="catalog-filters">
        <select value={selected} onChange={(e) => setSelected(e.target.value)}>
          {sessionList.map((s) => (
            <option key={`${s.season}-${s.round}`} value={`${s.season}-${s.round}`}>
              {s.season} R{s.round} — {s.label}
            </option>
          ))}
        </select>
        <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
          <option value="DEFICIT_REDUCTION">Deficit reduction (vs reference)</option>
          <option value="REFERENCE_BLEND">Blend with reference</option>
          <option value="OBSERVED">Observed (identity)</option>
          <option value="ENVELOPE_LOWER_BOUND">Envelope lower bound</option>
          <option value="ENVELOPE_UPPER_BOUND">Envelope upper bound</option>
        </select>
        <button onClick={run} disabled={loading}>
          {loading ? 'Analyzing…' : 'Analyze Envelope'}
        </button>
      </div>

      {error && <div className="catalog-error">Error: {error}</div>}

      {result && !valid && (
        <div className="catalog-empty">
          {result.status} — {result.reason || 'envelope not possible with current evidence'}
        </div>
      )}

      {result && valid && (
        <div className="catalog-detail">
          <div className="tv-headline">
            {result.driver}
            {result.reference_driver ? ` vs ${result.reference_driver}` : ''} · anchor lap {result.anchor_lap} · scope {result.envelope?.scope}
          </div>

          <table className="catalog-table">
            <thead>
              <tr>
                <th>Laps in band</th>
                <th>Mean band width</th>
                <th>Speed range (measured)</th>
                <th>Baseline (modeled)</th>
                <th>Reproduction</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{result.envelope?.laps_used.join(', ')}</td>
                <td>{result.envelope?.band_summary.mean_band_width_kmh.toFixed(1)} km/h</td>
                <td>
                  {result.envelope?.band_summary.overall_min_speed_kmh.toFixed(0)}–{result.envelope?.band_summary.overall_max_speed_kmh.toFixed(0)} km/h
                </td>
                <td>{result.model_baseline?.baseline_time_s.toFixed(3)} s</td>
                <td className="rg-ok">error {result.model_baseline?.reproduction_error_s} s</td>
              </tr>
            </tbody>
          </table>

          <h3>Measured band by region</h3>
          <table className="catalog-table">
            <thead>
              <tr>
                <th>Window (s)</th>
                <th>Lower</th>
                <th>Median</th>
                <th>Upper</th>
                <th>Width</th>
              </tr>
            </thead>
            <tbody>
              {(result.band_segments || []).map((b) => (
                <tr key={`${b.t_start_s}`}>
                  <td>{b.t_start_s.toFixed(0)}–{b.t_end_s.toFixed(0)}</td>
                  <td>{b.band_lower_mean_kmh.toFixed(0)} km/h</td>
                  <td>{b.band_centre_mean_kmh.toFixed(0)} km/h</td>
                  <td>{b.band_upper_mean_kmh.toFixed(0)} km/h</td>
                  <td className="muted">±{(b.band_width_mean_kmh / 2).toFixed(0)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>Scenario sensitivity</h3>
          <table className="catalog-table">
            <thead>
              <tr>
                <th>Parameter</th>
                <th>Modeled lap time</th>
                <th>Delta</th>
              </tr>
            </thead>
            <tbody>
              {(result.scenarios || []).map((s, i) => (
                <tr key={i}>
                  <td>{s.parameter}</td>
                  <td>{s.modeled_lap_time_s !== undefined ? `${s.modeled_lap_time_s.toFixed(3)} s` : '—'}</td>
                  <td className={s.delta_s !== undefined && s.delta_s < 0 ? 'rg-narrowing' : undefined}>
                    {fmt(s.delta_s)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small">
            Response: <strong>{result.sensitivity?.response.status}</strong>
            {result.sensitivity?.response.total_range_s !== undefined
              ? ` · measured range ${fmt(result.sensitivity.response.total_range_s)}`
              : ''}
            {' · '}{result.sensitivity?.note}
          </p>

          {result.regional_response && result.regional_response.length > 0 && (
            <>
              <h3>Largest regional responses</h3>
              <p className="muted small">
                {(result.regional_response || []).map((r) => (
                  <span key={r.t_start_s} style={{ marginRight: 12 }}>
                    {r.t_start_s.toFixed(0)}–{r.t_end_s.toFixed(0)} s: {fmt(r.scenario_delta_s)}
                  </span>
                ))}
                — model sensitivity by region, not sector causality.
              </p>
            </>
          )}

          {result.stint_response && (
            <>
              <h3>Stint sensitivity trend</h3>
              <p className="muted small">
                Mid-parameter scenario per measured stint lap:{' '}
                {result.stint_response.per_lap.map((p) => `L${p.lap_number} ${fmt(p.delta_s)}`).join(' · ')}
                {' '}→ trend {fmt(result.stint_response.sensitivity_trend_s_per_lap)} s/lap.
                Interpret alongside canonical degradation evidence — no new tyre model.
              </p>
            </>
          )}

          <div className="rg-accounting">
            <strong>Evidence</strong>
            <p>
              Historical evidence verdicts (lap evidence) and model sensitivity (here) are
              different epistemic objects. A supported hypothesis and a sensitive model
              do not together prove historical causation.
            </p>
          </div>

          <p className="muted small">Output hash: {result.output_hash}</p>
        </div>
      )}
    </div>
  )
}
