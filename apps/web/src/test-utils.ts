/* ============ shared test utilities: fetch mocking + real-shaped payloads ============
   Payloads mirror the deterministic backend contracts (see types.ts). The
   values are fixtures used ONLY to test rendering; the production UI never
   contains them. */
import { vi } from 'vitest'

export function mockFetch(routes: Record<string, unknown>): ReturnType<typeof vi.fn> {
  const fn = vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    for (const [pattern, handler] of Object.entries(routes)) {
      if (url.includes(pattern)) {
        const body = typeof handler === 'function' ? (handler as (u: string) => unknown)(url) : handler
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(body),
        } as Response)
      }
    }
    return Promise.resolve({
      ok: false,
      status: 404,
      json: () => Promise.resolve({ detail: 'not found' }),
    } as Response)
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

/* ---------- realistic 6N engineering-investigation payload (subset) ---------- */

export function investigationPayload(overrides?: Record<string, unknown>) {
  const ledger = [
    {
      evidence_id: 'evidence_001', evidence_type: 'FACT', source_phase: '6E',
      source_tool: 'attribute_lap_loss', source_reference: {}, source_hash: 'abc123',
      claim: 'observed lap delta at lap 6 (max-verstappen vs sergio-perez)',
      claim_class: 'OBSERVED', measured_value: 0.732, units: 's', state: 'OBSERVED',
      hypothesis_ids: [], assumptions: [], limitations: [], supports: false, contradicts: false,
    },
    {
      evidence_id: 'evidence_005', evidence_type: 'CALCULATION', source_phase: '6E',
      source_tool: 'attribute_lap_loss', source_reference: {}, source_hash: 'def456',
      claim: 'unexplained residual component (reported, never assigned)',
      claim_class: 'DERIVED', measured_value: -0.659, units: 's', state: 'UNRESOLVED',
      hypothesis_ids: [], assumptions: [], limitations: [], supports: false, contradicts: false,
    },
    {
      evidence_id: 'evidence_006', evidence_type: 'INFERENCE', source_phase: '6F',
      source_tool: 'fuse_lap_evidence', source_reference: {}, source_hash: 'ghi789',
      claim: 'formal evaluation of H1_corner_speed', claim_class: 'INFERRED',
      measured_value: null, units: null, state: 'CONTRADICTED',
      hypothesis_ids: ['H1_corner_speed'], assumptions: [], limitations: ['evidence-consistency, not causation'], supports: false, contradicts: true,
    },
    {
      evidence_id: 'evidence_007', evidence_type: 'INFERENCE', source_phase: '6F',
      source_tool: 'fuse_lap_evidence', source_reference: {}, source_hash: 'jkl012',
      claim: 'formal evaluation of H2_throttle', claim_class: 'INFERRED',
      measured_value: null, units: null, state: 'SUPPORTED',
      hypothesis_ids: ['H2_throttle'], assumptions: [], limitations: [], supports: true, contradicts: false,
    },
  ]
  const hypothesis_evaluations: Record<string, unknown> = {
    H1_corner_speed: {
      hypothesis_id: 'H1_corner_speed', requested: true, aggregate_state: 'CONTRADICTED',
      supporting_evidence: [], contradicting_evidence: ['evidence_006'], non_decisive_evidence: [],
      evidence_coverage: { items_total: 1, supporting: 0, contradicting: 1, non_decisive: 0 },
      falsification_status: 'CONTRADICTED', unresolved_contradictions: true,
    },
    H2_throttle: {
      hypothesis_id: 'H2_throttle', requested: true, aggregate_state: 'SUPPORTED',
      supporting_evidence: ['evidence_007'], contradicting_evidence: [], non_decisive_evidence: [],
      evidence_coverage: { items_total: 1, supporting: 1, contradicting: 0, non_decisive: 0 },
      falsification_status: 'SUPPORTED', unresolved_contradictions: false,
    },
    H3_braking: {
      hypothesis_id: 'H3_braking', requested: true, aggregate_state: 'NOT_SUPPORTED',
      supporting_evidence: [], contradicting_evidence: [], non_decisive_evidence: [],
      evidence_coverage: { items_total: 0, supporting: 0, contradicting: 0, non_decisive: 0 },
      falsification_status: 'NOT_SUPPORTED', unresolved_contradictions: false,
    },
    H4_tyre_state: {
      hypothesis_id: 'H4_tyre_state', requested: true, aggregate_state: 'NOT_TESTABLE',
      supporting_evidence: [], contradicting_evidence: [], non_decisive_evidence: [],
      evidence_coverage: { items_total: 0, supporting: 0, contradicting: 0, non_decisive: 0 },
      falsification_status: 'NOT_TESTABLE', unresolved_contradictions: false,
    },
    H5_race_control: {
      hypothesis_id: 'H5_race_control', requested: true, aggregate_state: 'INSUFFICIENT_EVIDENCE',
      supporting_evidence: [], contradicting_evidence: [], non_decisive_evidence: [],
      evidence_coverage: { items_total: 0, supporting: 0, contradicting: 0, non_decisive: 0 },
      falsification_status: 'INSUFFICIENT_EVIDENCE', unresolved_contradictions: false,
    },
    H6_drs: {
      hypothesis_id: 'H6_drs', requested: true, aggregate_state: 'MIXED_EVIDENCE',
      supporting_evidence: [], contradicting_evidence: [], non_decisive_evidence: [],
      evidence_coverage: { items_total: 0, supporting: 0, contradicting: 0, non_decisive: 0 },
      falsification_status: 'MIXED', unresolved_contradictions: false,
    },
  }
  return {
    status: 'VALID',
    question: { type: 'LAP_PERFORMANCE', scope: { season: 2023, round: 1, driver_a: 'max-verstappen', driver_b: 'sergio-perez', lap_number: 6, stint_number: null, session_type: 'RACE', pattern_id: null } },
    investigation_id: 'deadbeefdeadbeef',
    investigation_version: '6n_investigation_v1',
    question_type: 'LAP_PERFORMANCE',
    hypotheses_in_scope: ['H1_corner_speed', 'H2_throttle', 'H3_braking', 'H4_tyre_state', 'H5_race_control', 'H6_drs'],
    evidence_plan: [],
    evidence_ledger: ledger,
    collection: { status: 'VALID', raw_layer_statuses: {}, items_collected: ledger.length, bounded_by: {} },
    hypothesis_evaluations,
    falsification_gate: {
      any_unresolved_contradictions: true,
      establishable_hypotheses: ['H2_throttle'],
      hypotheses_with_unresolved_contradictions: ['H1_corner_speed'],
      rule: 'an established state requires zero unresolved contradictions',
    },
    counterfactual_candidates: [],
    executed_counterfactuals: [],
    evidence_conflicts: [],
    synthesis: {
      question_restated: { type: 'LAP_PERFORMANCE', scope: {} },
      established_facts: [], measured_findings: [],
      hypothesis_findings: {},
      contradictory_evidence: [], unavailable_evidence: [], counterfactual_findings: [],
      unresolved_questions: ['unresolved contradictions block an established explanation for: H1_corner_speed'],
      conclusion_state: 'MIXED_EVIDENCE',
      limitations: ['evidence-consistency is not proof'],
      decision_trace_refs: [],
    },
    decision_trace: [
      {
        trace_id: 'TRACE-001', statement: 'observed lap delta recorded from canonical facts',
        basis: ['evidence_001'], type: 'FACT', supporting_hypotheses: [], contradictory_evidence: [],
        status: 'OBSERVED',
      },
    ],
    investigation_snapshot: { input: {}, evidence_ids: [], evidence_source_hashes: {}, hypothesis_states: {}, counterfactual_ids: [] },
    provenance: { analytical_chain: ['6E', '6F', '6N'], method: 'deterministic', investigation_version: '6n_investigation_v1', layers_executed: ['6E', '6F'], provider: 'fastf1', source_tables: ['canonical_lap_times'] },
    epistemic_boundaries: ['SUPPORT is not PROOF', 'SIMILARITY is not CAUSALITY'],
    output_hash: 'cafecafecafecafe',
    ...overrides,
  }
}

/* ---------- counterfactual payload with profile samples ---------- */

export function counterfactualPayload(overrides?: Record<string, unknown>) {
  const n = 12
  return {
    analysis: 'simulate_telemetry_counterfactual', version: '1.1',
    status: 'VALID', season: 2023, round: 1, session_type: 'RACE',
    driver: 'sergio-perez', reference_driver: 'max-verstappen', lap_number: 6,
    signal: 'speed', intervention: { type: 'REMOVE_DEFICIT', fraction: 0.5 },
    epistemics: 'model sensitivity to a specified intervention; not a historical fact, not a prediction, not a causal proof',
    validation_gates: {
      telemetry: { status: 'PASS', detail: 'target n=140, reference n=140' },
      alignment: { status: 'PASS', detail: 'lap-relative grid step 0.25 s' },
      intervention: { status: 'PASS', detail: 'REMOVE_DEFICIT f=0.5' },
      simulator_mapping: { status: 'PASS', detail: 'speed has a deterministic lap-time model' },
      baseline_reproduction: { status: 'PASS', detail: 'error 0.00e+00 s' },
      sanity_bounds: { status: 'PASS', detail: 'finite=True' },
    },
    profile_summary: {
      signal: 'speed', unit: 'km/h', n_points: 140, grid_step_s: 0.25, coverage_s: 34.75,
      target_mean_speed_kmh: 201.5, target_max_speed_kmh: 312.4,
      transformed_mean_speed_kmh: 203.1, reference_mean_speed_kmh: 202.2,
    },
    profile_samples: {
      n_total_points: 140, n_samples: n, cap: 192, unit: 'km/h',
      sampling: 'deterministic evenly spaced decimation',
      t_s: Array.from({ length: n }, (_, i) => round(i * 3.2, 2)),
      target_kmh: Array.from({ length: n }, (_, i) => 120 + 10 * Math.sin(i / 2)),
      reference_kmh: Array.from({ length: n }, (_, i) => 122 + 10 * Math.sin(i / 2)),
      counterfactual_kmh: Array.from({ length: n }, (_, i) => 121 + 10 * Math.sin(i / 2)),
    },
    intervention_definition: 'v_cf(t) = v_target(t) + f * max(v_reference(t) - v_target(t), 0); removes fraction f of the measured speed deficit where it exists',
    model: {
      method: 'fixed-distance segment integration', segment_s: 2.0, n_segments: 18,
      units: 'speed km/h, time s',
      baseline_reproduction: { model_baseline_s: 93.8, measured_grid_duration_s: 93.8, error_s: 0, identity_intervention_delta_s: 0 },
    },
    baseline_result: { modeled_lap_time_s: 93.8 },
    counterfactual_result: { modeled_lap_time_s: 93.65 },
    counterfactual_delta_s: -0.15,
    deficit_closed_s: 0.15,
    delta_sign_convention: 'negative delta = intervened profile gains time',
    cross_check_6e: { note: 'informational correspondence', attribution_status: 'VALID_COMPARISON', attribution_estimated_pace_component_s: 0.4 },
    assumptions: ['speed is the only signal with a deterministic lap-time model'],
    limitations: ['lap-level only unless aggregated through the stint entry point'],
    provenance: { tables: ['canonical_telemetry'], provider: 'fastf1', counterfactual_version: '1.1', alignment: 'loss_attribution.ALPHA_RESAMPLE grid (0.25 s)' },
    output_hash: 'beefbeefbeefbeef',
    ...overrides,
  }
}

function round(v: number, d: number) { return Number(v.toFixed(d)) }

/* ---------- 6J envelope sweep payload ---------- */

export function envelopePayload(overrides?: Record<string, unknown>) {
  return {
    status: 'VALID', driver: 'sergio-perez', reference_driver: 'max-verstappen',
    anchor_lap: 6,
    scenario_definition: { type: 'DEFICIT_REDUCTION', parameters: [0.0, 0.25, 0.5, 0.75, 1.0], reference: 'max-verstappen' },
    scenarios: [
      { parameter: 0.0, status: 'VALID', modeled_lap_time_s: 93.8, delta_s: 0.0 },
      { parameter: 0.25, status: 'VALID', modeled_lap_time_s: 93.72, delta_s: -0.08 },
      { parameter: 0.5, status: 'VALID', modeled_lap_time_s: 93.65, delta_s: -0.15 },
      { parameter: 0.75, status: 'VALID', modeled_lap_time_s: 93.58, delta_s: -0.22 },
      { parameter: 1.0, status: 'VALID', modeled_lap_time_s: 93.5, delta_s: -0.3 },
    ],
    sensitivity: {
      response: { status: 'NON_LINEAR', total_range_s: 0.3 },
      note: 'each delta is a model sensitivity under the specified deterministic intervention',
    },
    ...overrides,
  }
}

/* ---------- session-context payload ---------- */

export function sessionContextPayload(overrides?: Record<string, unknown>) {
  return {
    season: 2023, round: 1, session_type: 'RACE', session: { event_name: 'Bahrain Grand Prix' },
    stints_by_driver: {
      'max-verstappen': [{ stint_number: 1, compound: 'hard', lap_start: 14, lap_end: 57, lap_count: 44, provider: 'fastf1' }],
      'sergio-perez': [{ stint_number: 1, compound: 'soft', lap_start: 30, lap_end: 57, lap_count: 28, provider: 'fastf1' }],
    },
    laps_by_driver: {
      'max-verstappen': Array.from({ length: 57 }, (_, i) => ({
        lap_number: i + 1, position: 1, time_s: 95 + i * 0.1, compound: 'hard', tyre_life: i + 1,
      })),
      'sergio-perez': Array.from({ length: 57 }, (_, i) => ({
        lap_number: i + 1, position: 2, time_s: 95.5 + i * 0.1, compound: 'soft', tyre_life: i - 28,
      })),
    },
    weather: {
      status: 'AVAILABLE', observations: 40, air_temp_c_first: 22.1, air_temp_c_last: 21.4,
      track_temp_c_first: 30.2, track_temp_c_last: 29.1, rainfall_observations: 0,
    },
    telemetry: {
      available: true, sample_count: 49000, drivers: 2,
      covered_laps: [4, 6, 8, 10, 12], analysis_grid_s: 0.25, policy: 'bounded Phase 6D coverage',
    },
    provenance: { tables: ['canonical_stints'], method: 'direct canonical row reads' },
    ...overrides,
  }
}
