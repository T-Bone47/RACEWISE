import { useCallback, useEffect, useState } from 'react'

interface Regime {
  regime_index: number
  start_lap: number
  end_lap: number
  lap_count: number
  slope_s_per_lap: number
  pattern: string
  mean_delta_s: number
  variance_s2: number
  mean_shift_s: number | null
  stints_spanned: number[]
  crosses_stint_boundary: boolean
  telemetry_state: string
  telemetry_lap_count: number
  speed_profile: {
    state: string
    mean_abs_distance_kmh: number | null
    distance_trend_kmh_per_lap: number | null
  }
  hypothesis_evolution: Array<{ hypothesis_id: string; summary: string }>
  residual: { residual_total_s: number | null; state: string }
  model_sensitivity: { status: string; delta_s?: number; reason?: string }
}

interface ChangePoint {
  transition_lap: number
  previous_pattern: string
  new_pattern: string
  detected: string
  context_alignment: Array<{ type: string; lap_number: number; relationship: string }>
  interpretation: string
}

interface TimelineEntry {
  kind: string
  lap_number: number
  end_lap?: number
  regime_index?: number
  pattern?: string
  change_point_type?: string
  transition_type?: string
  new?: string | number | boolean | null
}

interface RegimesResult {
  status: string
  reason?: string
  regime_count?: number
  comparable_lap_count?: number
  regimes?: Regime[]
  change_points?: ChangePoint[]
  rejected_change_points?: Array<{ candidate_transition_lap: number; reason: string }>
  race_timeline?: TimelineEntry[]
  unavailable_intervals?: Array<{ lap_number: number; status: string; reason: string | null }>
  output_hash?: string
}

interface SessionRef { season: number; round: number; label: string }

const KNOWN_SESSIONS: Array<{ season: number; round: number }> = [
  { season: 2025, round: 1 },
  { season: 2024, round: 14 },
  { season: 2023, round: 1 },
  { season: 2022, round: 4 },
]

const PATTERN_CLASS: Record<string, string> = {
  STABLE: 'rg-ok',
  WIDENING: 'rg-widening',
  NARROWING: 'rg-narrowing',
  INSUFFICIENT_EVIDENCE: 'muted',
}

function patternClass(p: string): string {
  return PATTERN_CLASS[p] ?? 'muted'
}

export default function PerformanceRegimeView() {
  const [sessions, setSessions] = useState<SessionRef[]>([])
  const [selected, setSelected] = useState('2023-1')
  const [result, setResult] = useState<RegimesResult | null>(null)
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
      const resp = await fetch(`/api/catalog/performance-regimes/${season}/${round}`)
      if (!resp.ok) throw new Error(`Regime request failed (${resp.status})`)
      setResult(await resp.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    finally {
      setLoading(false)
    }
  }, [selected])

  const sessionList: SessionRef[] =
    sessions.length > 0
      ? sessions
      : KNOWN_SESSIONS.map((s) => ({ ...s, label: `${s.season} R${s.round}` }))

  const valid = result?.status === 'VALID'

  return (
    <div className="catalog attribution-view">
      <h2>Performance Regime Analysis</h2>
      <p className="muted small">
        Deterministic segmentation of the comparable-lap gap series into regimes with
        documented thresholds (OLS slope, MIN_REGIME_LAPS=3). A change is <strong>not</strong> a
        cause: a transition temporally aligned with a context change is an association,
        never a causal claim. No confidence scores — states are DETECTED /
        NOT_DETECTED / INSUFFICIENT_EVIDENCE.
      </p>

      <div className="catalog-filters">
        <select value={selected} onChange={(e) => setSelected(e.target.value)}>
          {sessionList.map((s) => (
            <option key={`${s.season}-${s.round}`} value={`${s.season}-${s.round}`}>
              {s.season} R{s.round} — {s.label}
            </option>
          ))}
        </select>
        <button onClick={run} disabled={loading}>
          {loading ? 'Segmenting…' : 'Analyze Regimes'}
        </button>
      </div>

      {error && <div className="catalog-error">Error: {error}</div>}

      {result && !valid && (
        <div className="catalog-empty">
          {result.status} — {result.reason || 'regime analysis not possible with current evidence'}
        </div>
      )}

      {result && valid && (
        <div className="catalog-detail">
          <div className="tv-headline">
            {result.regime_count} regimes over {result.comparable_lap_count} comparable laps
          </div>

          <h3>Race timeline</h3>
          <table className="catalog-table">
            <thead>
              <tr>
                <th>Lap</th>
                <th>Kind</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {(result.race_timeline || []).map((e, i) => (
                <tr key={i}>
                  <td>
                    {e.end_lap !== undefined ? `${e.lap_number}–${e.end_lap}` : e.lap_number}
                  </td>
                  <td>{e.kind === 'REGIME' ? `Regime ${e.regime_index}` : e.kind === 'CHANGE_POINT' ? 'Change point' : e.transition_type}</td>
                  <td className={e.kind === 'REGIME' ? patternClass(e.pattern || '') : 'muted'}>
                    {e.kind === 'REGIME'
                      ? e.pattern
                      : e.kind === 'CHANGE_POINT'
                        ? `${e.change_point_type}`
                        : `→ ${e.new ?? '—'}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>Regimes</h3>
          <table className="catalog-table">
            <thead>
              <tr>
                <th>Regime</th>
                <th>Laps</th>
                <th>Pattern</th>
                <th>Slope (s/lap)</th>
                <th>Mean delta</th>
                <th>Telemetry</th>
                <th>Stints</th>
              </tr>
            </thead>
            <tbody>
              {(result.regimes || []).map((r) => (
                <tr key={r.regime_index}>
                  <td>R{r.regime_index}</td>
                  <td>{r.start_lap}–{r.end_lap} ({r.lap_count})</td>
                  <td className={patternClass(r.pattern)}>{r.pattern}</td>
                  <td>{r.slope_s_per_lap >= 0 ? '+' : ''}{r.slope_s_per_lap.toFixed(4)}</td>
                  <td>{r.mean_delta_s >= 0 ? '+' : ''}{r.mean_delta_s.toFixed(3)} s</td>
                  <td className="muted">
                    {r.telemetry_state === 'AVAILABLE' ? `${r.telemetry_lap_count} laps` : r.telemetry_state}
                  </td>
                  <td className="muted">
                    {r.crosses_stint_boundary ? `crosses ${r.stints_spanned.join(', ')}` : r.stints_spanned.join(', ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>Change points & context alignment</h3>
          {(result.change_points || []).length === 0 && (
            <p className="muted small">No change point met the deterministic thresholds (NOT_DETECTED).</p>
          )}
          {(result.change_points || []).map((c, i) => (
            <p className="muted small" key={i} style={{ marginBottom: 6 }}>
              <strong>Lap {c.transition_lap}: {c.previous_pattern} → {c.new_pattern}</strong>{' '}
              ({c.detected}).{' '}
              {c.context_alignment.length > 0
                ? `Aligned context: ${c.context_alignment.map(a => `${a.type} (${a.relationship})`).join(', ')}.`
                : 'No context transition within ±2 laps.'}{' '}
              {c.interpretation}
            </p>
          ))}
          {(result.rejected_change_points || []).length > 0 && (
            <p className="muted small">
              Rejected candidates (logged, never silently discarded):{' '}
              {(result.rejected_change_points || [])
                .map(r => `lap ${r.candidate_transition_lap} (${r.reason})`).join('; ')}
            </p>
          )}

          <h3>Per-regime evidence</h3>
          <table className="catalog-table">
            <thead>
              <tr>
                <th>Regime</th>
                <th>Speed-profile distance</th>
                <th>Residual</th>
                <th>Model sensitivity</th>
                <th>Hypotheses (non-insufficient)</th>
              </tr>
            </thead>
            <tbody>
              {(result.regimes || []).map((r) => (
                <tr key={r.regime_index}>
                  <td>R{r.regime_index}</td>
                  <td className="muted">
                    {r.speed_profile.mean_abs_distance_kmh !== null
                      ? `${r.speed_profile.mean_abs_distance_kmh.toFixed(1)} km/h mean`
                      : r.speed_profile.state}
                  </td>
                  <td className="muted">
                    {r.residual.residual_total_s !== null
                      ? `${r.residual.residual_total_s.toFixed(3)} s (${r.residual.state})`
                      : r.residual.state}
                  </td>
                  <td className="muted">
                    {r.model_sensitivity.status === 'VALID'
                      ? `${r.model_sensitivity.delta_s?.toFixed(3)} s @ f=0.5`
                      : r.model_sensitivity.status}
                  </td>
                  <td className="muted">
                    {r.hypothesis_evolution
                      .filter(h => h.summary !== 'INSUFFICIENT_EVIDENCE')
                      .map(h => `${h.hypothesis_id}: ${h.summary}`)
                      .join(' · ') || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {(result.unavailable_intervals || []).length > 0 && (
            <p className="muted small">
              Non-comparable / unavailable intervals preserved:{' '}
              {(result.unavailable_intervals || []).length} laps (reasons in the API payload).
            </p>
          )}

          <div className="rg-accounting">
            <strong>Limitations</strong>
            <p>
              Regimes are analytical intervals of comparable laps, not canonical stints.
              Residuals are reported, never assigned to a hypothesis. Model sensitivity is a
              property of the speed-profile model, not historical causation. Telemetry gaps
              are preserved as explicit unavailable intervals.
            </p>
          </div>

          <p className="muted small">Output hash: {result.output_hash}</p>
        </div>
      )}
    </div>
  )
}
