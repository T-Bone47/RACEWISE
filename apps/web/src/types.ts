/* ============ 6Q shared types — mirrors of the backend contracts ============ */

/* ---------- 6N investigation (mirror of investigation_synthesis.py) ---------- */

export interface QuestionScope {
  season: number
  round: number
  driver_a: string
  driver_b: string
  lap_number: number | null
  stint_number: number | null
  session_type: string
  pattern_id: string | null
}

export interface LedgerItem {
  evidence_id: string
  evidence_type: string
  source_phase: string
  source_tool: string
  source_reference: Record<string, unknown>
  source_hash: string
  claim: string
  claim_class: string
  measured_value: number | Record<string, unknown> | null
  units: string | null
  state: string | null
  hypothesis_ids: string[]
  assumptions: string[]
  limitations: string[]
  supports: boolean
  contradicts: boolean
}

export interface HypothesisEvaluation {
  hypothesis_id: string
  requested: boolean
  aggregate_state: string
  supporting_evidence: string[]
  contradicting_evidence: string[]
  non_decisive_evidence: string[]
  evidence_coverage: {
    items_total: number
    supporting: number
    contradicting: number
    non_decisive: number
  }
  falsification_status: string
  unresolved_contradictions: boolean
}

export interface Gate {
  any_unresolved_contradictions: boolean
  establishable_hypotheses: string[]
  hypotheses_with_unresolved_contradictions: string[]
  rule: string
}

export interface TraceEntry {
  trace_id: string
  statement: string
  basis: string[]
  type: string
  supporting_hypotheses: string[]
  contradictory_evidence: string[]
  status: string
}

export interface Conflict {
  conflict_id: string
  evidence_ids: string[]
  hypothesis_ids: string[]
  conflict_type: string
  description: string
  resolution_status: string
}

export interface CfCandidate {
  candidate_id: string
  kind: string
  status: string
  reason: string
  model_scope: string
  required_data: string[]
  missing_data: string[]
  telemetry_required: boolean
  baseline_available: boolean | null
}

export interface CfExecuted {
  candidate_id: string
  kind: string
  baseline: string
  intervention: { type: string; fraction: number }
  parameter: { signal: string; fraction: number }
  model: string
  result: Record<string, unknown>
  delta_s: number | null
  claim_class: string
  epistemics: string
}

export interface Synthesis {
  question_restated: { type: string; scope: QuestionScope }
  established_facts: Array<{
    evidence_id: string
    claim: string
    measured_value: number | null
    units: string | null
  }>
  measured_findings: Array<{
    evidence_id: string
    claim: string
    measured_value: number | null
    units: string | null
    method: string
  }>
  hypothesis_findings: Record<string, {
    aggregate_state: string
    falsification_status: string
    supporting_evidence: string[]
    contradicting_evidence: string[]
  }>
  contradictory_evidence: Array<{ evidence_id: string; claim: string; hypothesis_ids: string[] }>
  unavailable_evidence: Array<{ evidence_id?: string; kind?: string; claim?: string; state?: string; note?: string }>
  counterfactual_findings: Array<{
    candidate_id: string
    kind: string
    delta_s: number | null
    claim_class: string
    epistemics: string
  }>
  unresolved_questions: string[]
  conclusion_state: string
  limitations: string[]
  decision_trace_refs: string[]
}

export interface InvestigationResult {
  status: string
  reason?: string
  question: { type: string; scope: QuestionScope }
  investigation_id: string
  investigation_version: string
  question_type: string
  hypotheses_in_scope: string[]
  evidence_plan: Array<{ phase: string; tool: string; purpose: string }> | string[]
  evidence_ledger: LedgerItem[]
  collection: { status: string; raw_layer_statuses: Record<string, unknown>; items_collected: number; bounded_by: Record<string, unknown> }
  hypothesis_evaluations: Record<string, HypothesisEvaluation>
  falsification_gate: Gate
  counterfactual_candidates: CfCandidate[]
  executed_counterfactuals: CfExecuted[]
  evidence_conflicts: Conflict[]
  synthesis: Synthesis
  decision_trace: TraceEntry[]
  investigation_snapshot: { input: Record<string, unknown>; evidence_ids: string[]; evidence_source_hashes: Record<string, string>; hypothesis_states: Record<string, string>; counterfactual_ids: string[] }
  provenance: {
    analytical_chain: string[]
    method: string
    investigation_version: string
    layers_executed: string[]
    provider: string
    source_tables: string[]
  }
  epistemic_boundaries: string[]
  output_hash: string
}

/* ---------- 6O replay / comparison / memory ---------- */

export interface ReplayResult {
  status: string
  identical: boolean
  original_hash: string
  replay_hash: string | null
  difference_count: number
  differences: Array<{ path: string; old_value: unknown; new_value: unknown; category: string }>
  snapshot?: { snapshot_hash: string; investigation_id: string; output_hash: string }
}

export interface MemoryItem {
  memory_id: string
  statement: string
  evidence_ids: string[]
  source_investigation_ids: string[]
  hypothesis_ids: string[]
  evidence_type: string
  claim_class: string
  validity_status: string
  limitations: string[]
  scope: Record<string, unknown>
}

export interface MemoryResult {
  match_count: number
  matching_memory_items: MemoryItem[]
  policy: string
}

export interface EvidenceDelta {
  evidence_id_a: string | null
  evidence_id_b: string | null
  change_type: string
  old_state: string | null
  new_state: string | null
  old_value: unknown
  new_value: unknown
  claim_class: string | null
  interpretation_boundary?: string
}

export interface CompareResult {
  compatibility: { state: string; differing_scope_keys?: string[]; reason?: string }
  investigation_a: string | null
  investigation_b: string | null
  hash_a: string | null
  hash_b: string | null
  dimensions: Record<string, { state: string; detail?: Record<string, unknown> }>
  evidence_deltas: EvidenceDelta[]
  hypothesis_deltas: Array<{
    hypothesis_id: string
    old_state: string | null
    new_state: string | null
    state_changed: boolean
  }>
  falsification_deltas: Array<{ change_type: string; hypothesis_ids: string[]; evidence_ids?: string[] }>
  counterfactual_deltas: Array<{ change_type: string; candidate_id_a?: string | null; candidate_id_b?: string | null }>
  synthesis_delta: {
    old_conclusion_state: string | null
    new_conclusion_state: string | null
    transition: string
  }
  decision_trace_delta: { changed: unknown[]; unchanged_count: number; added_count: number; removed_count: number }
}

/* ---------- 6P graph ---------- */

export interface GraphNode {
  node_id: string
  node_type: string
  label: string
  canonical_reference: Record<string, unknown>
  metadata: Record<string, unknown>
  provenance: Record<string, unknown>
}

export interface GraphEdge {
  edge_id: string
  source_node: string
  target_node: string
  edge_type: string
  provenance: Record<string, unknown>
  source_reference: Record<string, unknown>
}

export interface GraphResult {
  graph_version: string
  graph_id: string
  investigation_id: string
  question_type: string
  node_count: number
  edge_count: number
  nodes: GraphNode[]
  edges: GraphEdge[]
  output_hash: string
  epistemic_boundaries: string[]
}

export interface GraphPathStep {
  step: string
  node_type: string
  via_edge_type: string | null
  via_edge_id: string | null
  via_provenance: Record<string, unknown> | null
}

export interface GraphPathResult {
  status: string
  investigation_id?: string
  target_node?: string
  path_length?: number
  path?: GraphPathStep[]
  reason?: string
}

export interface HypothesisTraceResult {
  status: string
  hypothesis_id: string
  investigations: string[]
  supporting_evidence: Array<{ node_id: string; node_type?: string; claim_class?: string | null; state?: string | null; measured_value?: unknown; units?: string | null; provenance: Record<string, unknown> }>
  contradicting_evidence: Array<{ node_id: string; node_type?: string; claim_class?: string | null; state?: string | null; measured_value?: unknown; units?: string | null; provenance: Record<string, unknown> }>
  non_decisive_evidence: Array<{ node_id: string; node_type?: string; claim_class?: string | null; state?: string | null; measured_value?: unknown; units?: string | null; provenance: Record<string, unknown> }>
  counterfactuals: Array<{ node_id: string; provenance: Record<string, unknown> }>
  note?: string
}

/* ---------- 6Q search ---------- */

export interface SearchResultItem {
  result_type: string
  label: string
  detail: string
  ref: Record<string, unknown>
  provenance: { matched_on: string; match_mode: string }
}

export interface SearchResponse {
  status: string
  query: string
  result_count: number
  results: SearchResultItem[]
  provenance: { method: string; note?: string }
}

/* ---------- closed vocabularies (mirrors of the backend) ---------- */

export const QUESTION_TYPES = [
  'LAP_PERFORMANCE',
  'STINT_PERFORMANCE',
  'RACE_GAP',
  'PERFORMANCE_REGIME',
  'CROSS_RACE_PATTERN',
  'HYPOTHESIS_EVALUATION',
  'COUNTERFACTUAL_ELIGIBILITY',
] as const

export const HYPOTHESIS_IDS = [
  'H1_corner_speed',
  'H2_throttle',
  'H3_braking',
  'H4_tyre_state',
  'H5_race_control',
  'H6_drs',
] as const

export const HYP_LABELS: Record<string, string> = {
  H1_corner_speed: 'H1 Corner Speed',
  H2_throttle: 'H2 Throttle',
  H3_braking: 'H3 Braking',
  H4_tyre_state: 'H4 Tyre State',
  H5_race_control: 'H5 Race Control',
  H6_drs: 'H6 DRS',
}

export const QUESTION_INPUTS: Record<string, Array<'lap_number' | 'stint_number' | 'pattern_id'>> = {
  LAP_PERFORMANCE: ['lap_number'],
  STINT_PERFORMANCE: ['stint_number'],
  RACE_GAP: [],
  PERFORMANCE_REGIME: [],
  CROSS_RACE_PATTERN: ['pattern_id'],
  HYPOTHESIS_EVALUATION: ['lap_number'],
  COUNTERFACTUAL_ELIGIBILITY: [],
}

/* chip class per hypothesis/state vocabulary (text is always shown too) */
export function stateChipClass(state: string | null | undefined): string {
  switch (state) {
    case 'SUPPORTED':
    case 'PARTIALLY_SUPPORTED':
    case 'SUPPORTED_BY_AVAILABLE_EVIDENCE':
    case 'ELIGIBLE':
      return 'st-supported'
    case 'NOT_SUPPORTED':
      return 'st-notsupported'
    case 'CONTRADICTED':
    case 'CONTRADICTORY':
      return 'st-contradicted'
    case 'MIXED_EVIDENCE':
      return 'st-mixed'
    case 'INSUFFICIENT_EVIDENCE':
      return 'st-insufficient'
    case 'MODELLED':
      return 'st-modelled'
    case 'OBSERVED':
      return 'st-observed'
    case 'NOT_TESTABLE':
    case 'NOT_REQUESTED':
    case 'UNAVAILABLE':
    case 'TELEMETRY_UNAVAILABLE':
    case 'UNSUPPORTED_MODEL':
    case 'INELIGIBLE':
      return 'st-untestable'
    default:
      return 'st-untestable'
  }
}
