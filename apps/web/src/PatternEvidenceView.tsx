import { useCallback, useState } from 'react'

interface OccurrenceRef {
  pattern_id: string
  season: number
  round: number
  circuit_name: string | null
  driver_pair: string[]
  regime_index: number
  lap_range: string
  pair_inverted_vs_canonical: boolean
}

interface UnderlyingCounts {
  valid_observations: number
  supported_count: number
  partially_supported_count: number
  not_supported_count: number
  contradicted_count: number
  not_testable_count: number
}

interface MatrixCell {
  mapped_state: string
  underlying_6g_summary: string | null
  underlying_counts: UnderlyingCounts
}

interface MatrixRow {
  ref: OccurrenceRef
  telemetry_status: string | null
  cells: Record<string, MatrixCell>
}

interface Profile {
  hypothesis_id: string
  hypothesis_statement: string
  aggregate_state: string
  evidence_consistency: string
  supporting_occurrences: OccurrenceRef[]
  contradicting_occurrences: OccurrenceRef[]
  not_supported_occurrences: OccurrenceRef[]
  not_testable_occurrences: OccurrenceRef[]
  insufficient_occurrences: OccurrenceRef[]
  evidence_coverage: Record<string, number>
  independent_race_count: number
  independent_circuit_count: number
  independent_season_count: number
  first_occurrence: number[]
  last_occurrence: number[]
  falsification_status: string
  falsification_note?: string
}

interface EvidenceResult {
  status: string
  reason?: string
  question?: string
  pattern_id?: string
  occurrence_count?: number
  independent_race_count?: number
  independent_circuit_count?: number
  independent_season_count?: number
  cross_race_falsification_check?: { result: string; note: string }
  hypothesis_profiles?: Profile[]
  evidence_matrix?: { columns: string[]; rows: MatrixRow[]; note: string }
  contradiction_summary?: {
    hypotheses_with_contradictions: string[]
    contradicting_occurrence_refs: OccurrenceRef[]
    policy: string
  }
  falsification_summary?: Record<string, {
    falsification_status: string
    falsification_note?: string
    contradicting_refs: OccurrenceRef[]
    supporting_refs: OccurrenceRef[]
    not_testable_refs: OccurrenceRef[]
    unavailable_refs: OccurrenceRef[]
  }>
  context_comparison?: Array<{
    facet: string
    occurrence_count: number
    races: string[]
    aggregate_state_per_hypothesis: Record<string, string>
    note: string
  }>
  residual_summary?: {
    residual_pattern: string
    per_occurrence: Array<{ ref: OccurrenceRef; residual_state: string; residual_mean_s: number | null }>
    note: string
    residual_ols_slope_s_per_occurrence?: number
  }
  sensitivity_summary?: {
    status: string
    intervention_definition: string
    interpretation_bound: string
    note?: string
    telemetry_supported_occurrences?: number
    mean_s?: number
    min_s?: number
    max_s?: number
    spread_s?: number
    per_occurrence: Array<{
      ref: OccurrenceRef
      sensitivity_status: string | null
      sensitivity_delta_s: number | null
      sensitivity_parameter: number | null
    }>
  }
  evidence_vs_sensitivity?: {
    per_hypothesis: Record<string, {
      aggregate_state: string
      model_sensitivity_status: string | null
      interpretation: string
      note: string
    }>
    purpose: string
  }
  unavailable_evidence?: {
    hypotheses_without_informative_evidence: string[]
    hypotheses_with_not_testable_occurrences: string[]
    policy: string
  }
  occurrence_truncation_note?: string | null
  limitations?: string[]
  epistemic_boundaries?: string[]
  provenance?: { analytical_chain: string[]; method: string; provider: string }
  output_hash?: string
}

const HYP_LABELS: Record<string, string> = {
  H1_corner_speed: 'Corner speed',
  H2_throttle: 'Throttle',
  H3_braking: 'Braking',
  H4_tyre_state: 'Tyre state',
  H5_race_control: 'Race control',
  H6_drs: 'DRS',
}

// Visual distinction between measured evidence, model output, missing data
// and contradiction — deliberately NOT a score, meter, or ranking bar.
const STATE_CLASS: Record<string, string> = {
  SUPPORTED: 'ev-support',
  PARTIALLY_SUPPORTED: 'ev-partial',
  CONTRADICTED: 'ev-contradicted',
  NOT_SUPPORTED: 'ev-notsupported',
  NOT_TESTABLE: 'ev-missing',
  INSUFFICIENT_EVIDENCE: 'ev-missing',
  CONTRADICTORY: 'ev-contradicted',
  VARIABLE: 'ev-variable',
  CONSISTENTLY_SUPPORTED: 'ev-support',
  MOSTLY_SUPPORTED: 'ev-partial',
  CONSISTENTLY_NOT_SUPPORTED: 'ev-notsupported',
}

function refLabel(r: OccurrenceRef): string {
  return `${r.season} R${r.round} regime ${r.regime_index} (${r.lap_range})`
}

function StateChip({ state }: { state: string }) {
  return (
    <span className={`ev-chip ${STATE_CLASS[state] || 'ev-missing'}`}>
      {state.replace(/_/g, ' ')}
    </span>
  )
}

export default function PatternEvidenceView() {
  const [patternId, setPatternId] = useState('')
  const [maxOccurrences, setMaxOccurrences] = useState(6)
  const [result, setResult] = useState<EvidenceResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = useCallback(async () => {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const params = new URLSearchParams({
        pattern_id: patternId.trim(),
        max_occurrences: String(maxOccurrences),
      })
      const resp = await fetch(`/api/catalog/performance-pattern-evidence?${params}`)
      if (!resp.ok) {
        const detail = await resp.json().catch(() => null)
        throw new Error(detail?.detail || `Evidence request failed (${resp.status})`)
      }
      const j = (await resp.json()) as EvidenceResult
      if (j.status !== 'VALID') throw new Error(j.reason || `status ${j.status}`)
      setResult(j)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [patternId, maxOccurrences])

  return (
    <div className="panel">
      <h2>Phase 6M — Cross-Race Hypothesis &amp; Evidence</h2>
      <p className="muted small">
        Investigates how the measured evidence behind one recurring cross-race
        pattern behaves across its independent occurrences. Evidence states are
        deterministic classifications of 6F/6G observations — not confidence
        scores. A consistent aggregate is not causation; no falsification found
        is not confirmation; residuals are never assigned.
      </p>
      <div className="controls">
        <input
          type="text"
          placeholder="pattern_id from Phase 6L patterns view"
          value={patternId}
          onChange={(e) => setPatternId(e.target.value)}
          style={{ minWidth: 260 }}
        />
        <label>
          max occurrences:{' '}
          <select value={maxOccurrences} onChange={(e) => setMaxOccurrences(Number(e.target.value))}>
            {[2, 3, 4, 5, 6, 7, 8].map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>
        <button onClick={run} disabled={loading || !patternId.trim()}>
          {loading ? 'Analyzing…' : 'Investigate evidence'}
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      {result && (
        <div>
          <p className="muted small">
            pattern <code>{result.pattern_id}</code> · {result.occurrence_count} occurrences ·{' '}
            {result.independent_race_count} races · {result.independent_circuit_count} circuits ·{' '}
            {result.independent_season_count} seasons · cross-race check:{' '}
            {result.cross_race_falsification_check?.result} · hash{' '}
            <code>{result.output_hash}</code>
          </p>
          {result.occurrence_truncation_note && (
            <p className="muted small">{result.occurrence_truncation_note}</p>
          )}

          <h3>Evidence matrix (rows = occurrences, columns = hypotheses)</h3>
          <table className="catalog-table">
            <thead>
              <tr>
                <th>Occurrence</th>
                <th>Telemetry</th>
                {result.evidence_matrix!.columns.map((h) => (
                  <th key={h}>{HYP_LABELS[h] || h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.evidence_matrix!.rows.map((row, i) => (
                <tr key={i}>
                  <td className="small">{refLabel(row.ref)}</td>
                  <td className="muted small">{row.telemetry_status || '—'}</td>
                  {result.evidence_matrix!.columns.map((h) => {
                    const c = row.cells[h]
                    return (
                      <td key={h}>
                        <StateChip state={c.mapped_state} />
                        <div className="muted small" title={c.underlying_6g_summary || ''}>
                          {c.underlying_counts.valid_observations} obs
                          {c.underlying_counts.contradicted_count > 0 &&
                            ` · ${c.underlying_counts.contradicted_count} contra`}
                        </div>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small">{result.evidence_matrix!.note}</p>

          <h3>Per-hypothesis aggregate states</h3>
          <table className="catalog-table">
            <thead>
              <tr>
                <th>Hypothesis</th>
                <th>Aggregate</th>
                <th>Consistency</th>
                <th>Coverage</th>
                <th>Falsification</th>
              </tr>
            </thead>
            <tbody>
              {result.hypothesis_profiles!.map((p) => (
                <tr key={p.hypothesis_id}>
                  <td className="small" title={p.hypothesis_statement}>
                    {HYP_LABELS[p.hypothesis_id] || p.hypothesis_id}
                  </td>
                  <td><StateChip state={p.aggregate_state} /></td>
                  <td>{p.evidence_consistency}</td>
                  <td className="muted small">
                    {p.evidence_coverage.informative_occurrences} informative ·{' '}
                    {p.evidence_coverage.not_testable_occurrences} not-testable ·{' '}
                    {p.evidence_coverage.insufficient_occurrences} insufficient
                  </td>
                  <td className="small">{p.falsification_status}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {result.contradiction_summary &&
            result.contradiction_summary.hypotheses_with_contradictions.length > 0 && (
              <div className="rg-accounting">
                <strong>Contradictions (preserved verbatim, never averaged away)</strong>
                <ul>
                  {result.contradiction_summary.contradicting_occurrence_refs.map((r, i) => (
                    <li key={i} className="small">
                      {HYP_LABELS[
                        result.contradiction_summary!.hypotheses_with_contradictions[
                          i % result.contradiction_summary!.hypotheses_with_contradictions.length
                        ]
                      ] || ''}{' '}
                      — {refLabel(r)}
                    </li>
                  ))}
                </ul>
              </div>
            )}

          <h3>Residual (reported, never assigned)</h3>
          <p className="muted small">
            pattern: {result.residual_summary!.residual_pattern}
            {result.residual_summary!.residual_ols_slope_s_per_occurrence !== undefined &&
              ` (OLS ${result.residual_summary!.residual_ols_slope_s_per_occurrence}s/occurrence)`}{' '}
            — {result.residual_summary!.note}
          </p>

          <h3>Model sensitivity (model property, not historical effect)</h3>
          <p className="muted small">
            status {result.sensitivity_summary!.status}
            {result.sensitivity_summary!.status === 'VALID' &&
              ` · mean ${result.sensitivity_summary!.mean_s}s · spread ${result.sensitivity_summary!.spread_s}s`}
            {result.sensitivity_summary!.note && ` — ${result.sensitivity_summary!.note}`}
          </p>
          <p className="muted small">{result.sensitivity_summary!.interpretation_bound}</p>

          <h3>Evidence vs sensitivity</h3>
          <table className="catalog-table">
            <thead>
              <tr>
                <th>Hypothesis</th>
                <th>Evidence</th>
                <th>Model response</th>
                <th>Alignment</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(result.evidence_vs_sensitivity!.per_hypothesis).map(([h, v]) => (
                <tr key={h}>
                  <td>{HYP_LABELS[h] || h}</td>
                  <td><StateChip state={v.aggregate_state} /></td>
                  <td className="muted small">{v.model_sensitivity_status || '—'}</td>
                  <td className="small">{v.interpretation}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {result.context_comparison && result.context_comparison.length > 0 && (
            <>
              <h3>Context associations (descriptive only)</h3>
              <table className="catalog-table">
                <thead>
                  <tr>
                    <th>Facet</th>
                    <th>Occurrences</th>
                    <th>Races</th>
                  </tr>
                </thead>
                <tbody>
                  {result.context_comparison.map((f, i) => (
                    <tr key={i}>
                      <td className="small">{f.facet}</td>
                      <td>{f.occurrence_count}</td>
                      <td className="muted small">{f.races.join(', ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          <div className="rg-accounting">
            <strong>Unavailable evidence (missing data is preserved, never negative evidence)</strong>
            <p className="muted small">
              without informative evidence: {result.unavailable_evidence!.hypotheses_without_informative_evidence.join(', ') || 'none'}{' '}
              · with not-testable occurrences: {result.unavailable_evidence!.hypotheses_with_not_testable_occurrences.join(', ') || 'none'}
            </p>
            <strong>Limitations</strong>
            <ul>
              {(result.limitations || []).map((l, i) => (
                <li key={i} className="small">{l}</li>
              ))}
            </ul>
            <strong>Provenance</strong>
            <p className="muted small">
              analytical chain: {result.provenance!.analytical_chain.join(' → ')} · provider{' '}
              {result.provenance!.provider}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
