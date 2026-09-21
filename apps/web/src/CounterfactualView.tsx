import { useCallback, useEffect, useState } from 'react'

interface Gate {
  status: string
  detail: string
}

interface CounterfactualResult {
  status: string
  reason?: string
  driver?: string
  reference_driver?: string | null
  lap_number?: number
  signal?: string
  intervention?: { type: string; fraction: number }
  epistemics?: string
  validation_gates?: Record<string, Gate>
  profile_summary?: {
    n_points: number
    grid_step_s: number
    coverage_s: number
    target_mean_speed_kmh: number
    transformed_mean_speed_kmh: number
    reference_mean_speed_kmh: number | null
  }
  baseline_result?: { modeled_lap_time_s: number }
  counterfactual_result?: { modeled_lap_time_s: number }
  counterfactual_delta_s?: number
  deficit_closed_s?: number
  delta_sign_convention?: string
  cross_check_6e?: { attribution_status?: string; attribution_estimated_pace_component_s?: number | null } | null
  output_hash?: string
}

interface SessionRef { season: number; round: number; label: string }

const KNOWN_SESSIONS: Array<{ season: number; round: number }> = [
  { season: 2025, round: 1 },
  { season: 2024, round: 14 },
  { season: 2023, round: 1 },
  { season: 2022, round: 4 },
]

const GATE_OK = new Set(['PASS'])

export default function CounterfactualView() {
  const [sessions, setSessions] = useState<SessionRef[]>([])
  const [selected, setSelected] = useState('2023-1')
  const [fraction, setFraction] = useState(0.5)
  const [result, setResult] = useState<CounterfactualResult | null>(null)
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
      const resp = await fetch(`/api/catalog/counterfactual/${season}/${round}?fraction=${fraction}`)
      if (!resp.ok) throw new Error(`Counterfactual request failed (${resp.status})`)
      setResult(await resp.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    finally {
      setLoading(false)
    }
  }, [selected, fraction])

  const sessionList: SessionRef[] =
    sessions.length > 0
      ? sessions
      : KNOWN_SESSIONS.map((s) => ({ ...s, label: `${s.season} R${s.round}` }))

  const valid = result?.status === 'VALID'
  const gates = result?.validation_gates || {}
  const fmt = (v: number | null | undefined, d = 3) =>
    v === null || v === undefined ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(d)} s`

  return (
    <div className="catalog attribution-view">
      <h2>Validated Telemetry Counterfactual</h2>
      <p className="muted small">
        Under a bounded speed-profile intervention, the deterministic fixed-distance lap-time
        model measures its own sensitivity. A counterfactual result is <em>not</em> a historical
        fact, a prediction, or a causal proof. Only speed has a lap-time model; other signals
        are reported as unsupported rather than approximated.
      </p>

      <div className="catalog-filters">
        <select value={selected} onChange={(e) => setSelected(e.target.value)}>
          {sessionList.map((s) => (
            <option key={`${s.season}-${s.round}`} value={`${s.season}-${s.round}`}>
              {s.season} R{s.round} — {s.label}
            </option>
          ))}
        </select>
        <label className="small">
          fraction&nbsp;
          <input
            type="number" min={0} max={1} step={0.05} value={fraction}
            onChange={(e) => setFraction(Number(e.target.value))}
            style={{ width: 70 }}
          />
        </label>
        <button onClick={run} disabled={loading}>
          {loading ? 'Simulating…' : 'Simulate Counterfactual'}
        </button>
      </div>

      {error && <div className="catalog-error">Error: {error}</div>}

      {result && !valid && (
        <div className="catalog-empty">
          {result.status} — {result.reason || 'counterfactual not possible with current evidence'}
        </div>
      )}

      {result && valid && (
        <div className="catalog-detail">
          <div className="tv-headline">
            Lap {result.lap_number}: {result.driver} (target) vs {result.reference_driver} (reference)
          </div>

          <div className="cf-intervention">
            <strong>INTERVENTION</strong>&nbsp; {result.intervention?.type} · fraction{' '}
            {result.intervention?.fraction} — removes that fraction of the measured speed deficit
            where the reference is faster. A mathematical transformation, not "better driving".
          </div>

          <table className="catalog-table">
            <thead>
              <tr>
                <th>Baseline (modeled)</th>
                <th>Counterfactual (modeled)</th>
                <th>Delta</th>
                <th>Deficit closed</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{result.baseline_result?.modeled_lap_time_s.toFixed(3)} s</td>
                <td>{result.counterfactual_result?.modeled_lap_time_s.toFixed(3)} s</td>
                <td className={result.counterfactual_delta_s !== undefined && result.counterfactual_delta_s < 0 ? 'rg-narrowing' : 'rg-widening'}>
                  {fmt(result.counterfactual_delta_s)}
                </td>
                <td>{fmt(result.deficit_closed_s)}</td>
              </tr>
            </tbody>
          </table>
          <p className="muted small">{result.delta_sign_convention}</p>

          <h3>Validation gates</h3>
          <ul className="cf-gates">
            {Object.entries(gates).map(([name, gate]) => (
              <li key={name} className={GATE_OK.has(gate.status) ? 'rg-ok' : 'rg-warn'}>
                <strong>{gate.status === 'PASS' ? '✓' : '·'}</strong> {name}
                {gate.detail ? <span className="muted"> — {gate.detail}</span> : null}
              </li>
            ))}
          </ul>

          {result.profile_summary && (
            <p className="muted small">
              Profile: {result.profile_summary.n_points} points @ {result.profile_summary.grid_step_s} s ·
              coverage {result.profile_summary.coverage_s} s · mean {result.profile_summary.target_mean_speed_kmh} → {result.profile_summary.transformed_mean_speed_kmh} km/h
              {result.profile_summary.reference_mean_speed_kmh !== null
                ? ` (reference ${result.profile_summary.reference_mean_speed_kmh} km/h)`
                : ''}
            </p>
          )}

          {result.cross_check_6e && (
            <p className="muted small">
              6E cross-check (informational, different quantity — never merged): attribution status{' '}
              {result.cross_check_6e.attribution_status ?? 'unavailable'}
              {result.cross_check_6e.attribution_estimated_pace_component_s !== null &&
              result.cross_check_6e.attribution_estimated_pace_component_s !== undefined
                ? `, estimated pace component ${result.cross_check_6e.attribution_estimated_pace_component_s} s`
                : ''}
              .
            </p>
          )}

          <div className="rg-accounting">
            <strong>Interpretation</strong>
            <p>
              {result.epistemics}. The delta quantifies how strongly the lap-time model responds
              to the specified intervention — it does not establish that the deficit caused the
              historical gap, and the 6E residual applies at full removal.
            </p>
          </div>

          <p className="muted small">Output hash: {result.output_hash}</p>
        </div>
      )}
    </div>
  )
}
