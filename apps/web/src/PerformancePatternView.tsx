import { useCallback, useState } from 'react'

interface Occurrence {
  season: number
  round: number
  circuit_name: string | null
  regime_index: number
  lap_range: string
  driver_pair: string[]
  trend_classification: string
  slope_s_per_lap: number | null
  lap_count: number
  residual_state: string
  residual_mean_s: number | null
  envelope_width_mean_kmh: number | null
  sensitivity_status: string
  sensitivity_delta_s: number | null
  sensitivity_parameter: number | null
  telemetry_status: string
  telemetry_lap_count: number
  compound_summary: string[]
  stint_overlap: number[]
  pit_overlap: boolean
  race_control_overlap: boolean
  hypothesis_state_summary: Record<string, string>
  normalized_shape: number[] | null
  pair_inverted_vs_canonical: boolean
}

interface MatchEntry {
  seed: { season: number; round: number; regime_index: number }
  member: { season: number; round: number; regime_index: number }
  structure_state: string
  structural_score: number | null
  trajectory: string | null
  comparability: string
}

interface Pattern {
  pattern_id: string
  coarse_group: string
  canonical_signature: {
    trend_classification: string
    slope_state: string | null
    duration_bucket: string
    residual_state: string
    telemetry_status: string
  }
  occurrence_count: number
  independent_races: number
  occurrences: Occurrence[]
  seasons: number[]
  circuits: string[]
  repeat_type: string
  comparison_matrix: MatchEntry[]
  context_summary: { facets: Array<{ facet: string; occurrence_count: number; races: string[] }> }
  hypothesis_summary: Record<string, {
    consistency: string
    statuses: string[]
    race_regime_refs: string[]
  }>
  falsification_summary: {
    supporting_refs: string[]
    contradicting_refs: string[]
    not_testable_refs: string[]
  }
  residual_summary: { state: string; per_occurrence: string[] }
  sensitivity_summary: {
    state: string
    values?: Array<{ race: string; regime_index: number; delta_s: number }>
    sensitivity_spread_s?: number
  }
  telemetry_summary: { statuses: string[]; telemetry_lap_counts: number[] }
  recurrence_classification: string
  limitations: string[]
}

interface PatternsResult {
  status: string
  reason?: string
  corpus?: { eligible_races: number; analyzed_races: number }
  signature_count?: number
  structural_group_count?: number
  non_recurring_group_count?: number
  pattern_count?: number
  patterns?: Pattern[]
  output_hash?: string
}

const KNOWN_SEASON_SETS: Array<{ value: string; label: string }> = [
  { value: '2022,2023,2024,2025', label: '2022–2025' },
  { value: '2023,2024,2025', label: '2023–2025' },
  { value: '2023,2024', label: '2023–2024' },
  { value: '2023', label: '2023 only' },
]

const HYP_LABELS: Record<string, string> = {
  H1_corner_speed: 'Corner speed',
  H2_throttle: 'Throttle',
  H3_braking: 'Braking',
  H4_tyre_state: 'Tyre state',
  H5_race_control: 'Race control',
  H6_drs: 'DRS',
}

function ShapeSpark({ shape }: { shape: number[] | null }) {
  if (!shape || shape.length < 2) return <span className="muted small">shape unavailable</span>
  const min = Math.min(...shape)
  const max = Math.max(...shape)
  const span = max - min || 1
  const w = 72
  const h = 20
  const pts = shape
    .map((v, i) => `${(i / (shape.length - 1)) * w},${h - ((v - min) / span) * h}`)
    .join(' ')
  return (
    <svg width={w} height={h} aria-label="normalized regime shape">
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  )
}

export default function PerformancePatternView() {
  const [seasonScope, setSeasonScope] = useState('2022,2023,2024,2025')
  const [maxRaces, setMaxRaces] = useState(6)
  const [result, setResult] = useState<PatternsResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = useCallback(async () => {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const params = new URLSearchParams({
        seasons: seasonScope,
        max_races: String(maxRaces),
      })
      const resp = await fetch(`/api/catalog/performance-patterns?${params}`)
      if (!resp.ok) throw new Error(`Pattern request failed (${resp.status})`)
      setResult(await resp.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [seasonScope, maxRaces])

  const valid = result?.status === 'VALID'

  return (
    <div className="catalog attribution-view">
      <h2>Cross-Race Performance Patterns</h2>
      <p className="muted small">
        Deterministic recurrence detection over per-race performance regimes (Phase 6K
        signatures, documented thresholds, no clustering, no embeddings). A recurring pattern
        is an observation of repetition across independent race instances — it is{' '}
        <strong>not</strong> a cause, not a significance claim, and races/drivers are never
        ranked. No confidence scores — states are deterministic classifications.
      </p>

      <div className="catalog-filters">
        <select value={seasonScope} onChange={(e) => setSeasonScope(e.target.value)}>
          {KNOWN_SEASON_SETS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        <select value={maxRaces} onChange={(e) => setMaxRaces(Number(e.target.value))}>
          {[4, 6, 8, 10].map((n) => (
            <option key={n} value={n}>
              max {n} races
            </option>
          ))}
        </select>
        <button onClick={run} disabled={loading}>
          {loading ? 'Matching…' : 'Analyze Patterns'}
        </button>
      </div>

      {error && <div className="catalog-error">Error: {error}</div>}

      {result && !valid && (
        <div className="catalog-empty">
          {result.status} — {result.reason || 'pattern analysis not possible with current evidence'}
        </div>
      )}

      {result && valid && (
        <div className="catalog-detail">
          <div className="tv-headline">
            {result.pattern_count} recurring patterns · {result.signature_count} regime
            signatures · {result.corpus?.analyzed_races}/{result.corpus?.eligible_races} races
            analyzed
          </div>
          <p className="muted small">
            {result.structural_group_count} structural groups;
            {' '}{result.non_recurring_group_count} candidate sets observed in fewer than 2
            independent races (not reported as recurring). Output hash: {result.output_hash}
          </p>

          {(result.patterns || []).map((p) => (
            <div key={p.pattern_id} className="pp-pattern">
              <h3>
                Pattern {p.pattern_id.slice(0, 8)} · {p.canonical_signature.trend_classification}{' '}
                · observed in {p.independent_races} independent races ({p.occurrence_count}{' '}
                regimes)
              </h3>
              <p className="muted small">
                Repeat type: {p.repeat_type} · telemetry: {p.canonical_signature.telemetry_status}{' '}
                · residual: {p.canonical_signature.residual_state} · circuits:{' '}
                {p.circuits.join(', ')}
              </p>

              <table className="catalog-table">
                <thead>
                  <tr>
                    <th>Race</th>
                    <th>Circuit</th>
                    <th>Regime laps</th>
                    <th>Slope (s/lap)</th>
                    <th>Laps</th>
                    <th>Sensitivity Δs (f=0.5)</th>
                    <th>Shape (regime-relative)</th>
                    <th>Context</th>
                  </tr>
                </thead>
                <tbody>
                  {p.occurrences.map((o) => (
                    <tr key={`${o.season}-${o.round}-${o.regime_index}`}>
                      <td>
                        {o.season} R{o.round}
                        {o.pair_inverted_vs_canonical && (
                          <span className="muted small"> (pair inverted)</span>
                        )}
                      </td>
                      <td>{o.circuit_name || '—'}</td>
                      <td>{o.lap_range}</td>
                      <td>{o.slope_s_per_lap ?? '—'}</td>
                      <td>{o.lap_count}</td>
                      <td>
                        {o.sensitivity_status === 'VALID' ? o.sensitivity_delta_s : 'unavailable'}
                      </td>
                      <td>
                        <ShapeSpark shape={o.normalized_shape} />
                      </td>
                      <td className="muted small">
                        {o.compound_summary.join('/')} · stints {o.stint_overlap.join(',')}
                        {o.pit_overlap ? ' · pit' : ''}
                        {o.race_control_overlap ? ' · RC' : ''}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <p className="muted small">
                Structural matches (seed vs members, documented thresholds):{' '}
                {p.comparison_matrix.map((m, i) => (
                  <span key={i}>
                    {i > 0 && '; '}
                    {m.structure_state.replace(/_STRUCTURE$/, '')} ({m.structural_score ?? '—'},
                    {' '}trajectory {m.trajectory || '—'})
                  </span>
                ))}
              </p>

              <h4>Hypothesis consistency (6F vocabulary, never collapsed)</h4>
              <table className="catalog-table">
                <thead>
                  <tr>
                    <th>Hypothesis</th>
                    <th>Consistency</th>
                    <th>Per-regime statuses</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(p.hypothesis_summary).map(([h, v]) => (
                    <tr key={h}>
                      <td>{HYP_LABELS[h] || h}</td>
                      <td>{v.consistency}</td>
                      <td className="muted small">{v.statuses.join(' → ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {p.falsification_summary.contradicting_refs.length > 0 && (
                <p className="muted small">
                  Contradicting evidence preserved (never averaged away):{' '}
                  {p.falsification_summary.contradicting_refs.join('; ')}
                </p>
              )}
              {p.sensitivity_summary.state === 'MEASURED' && (
                <p className="muted small">
                  Model sensitivity under the same intervention (DEFICIT_REDUCTION f=0.5):{' '}
                  {(p.sensitivity_summary.values || [])
                    .map((v) => `${v.race}: ${v.delta_s}s`)
                    .join(', ')}{' '}
                  — a model property, not historical causation.
                </p>
              )}

              <div className="rg-accounting">
                <strong>Limitations</strong>
                <ul>
                  {p.limitations.map((l, i) => (
                    <li key={i}>{l}</li>
                  ))}
                </ul>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
