/* ============ universal question panel tests ============
   The panel's job is to render engine truth without embellishing it. These
   tests pin the properties that matter epistemically: statuses are shown
   verbatim, residuals are never hidden, counterfactuals keep their MODELLED
   label, and a clarification question is rendered as a question rather than an
   error. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import UniversalQuestion from './UniversalQuestion'

const ANSWER = {
  answer_status: 'PARTIALLY_ANSWERABLE',
  question: 'Why did Verstappen lose time to Perez on lap 6?',
  short_answer: '+0.732 s observed; 0.659 s remains unexplained by the mechanisms tested.',
  scope: { season: 2023, round: 1, driver_a: 'max-verstappen', driver_b: 'sergio-perez' },
  observations: [
    { statement: 'Observed lap delta (measured)', value: 0.732, unit: 's', claim_class: 'OBSERVED', corroborated_by: ['attribute_lap_loss'] },
  ],
  spatial: [{ scope: 'sector 2', measured_delta_s: 0.411, telemetry_estimated_loss_s: 0.7082 }],
  hypotheses: [
    { hypothesis_id: 'H1_corner_speed', state: 'CONTRADICTED_OR_NOT_SUPPORTED', supporting_evidence_ids: ['a'], contradicting_evidence_ids: ['b'] },
  ],
  residuals: [{ statement: '0.659 s remains unexplained', value: -0.659, unit: 's' }],
  counterfactuals: [{ statement: 'Modelled lap-time change', value: -0.21, claim_class: 'MODELLED' }],
  not_established: [{ statement: 'H6_drs', reason: 'requires telemetry data, unavailable for this session' }],
  limitations: ['telemetry'],
  missing_evidence: ['race_control'],
  engine_conclusion: 'Residual is reported, not assigned to any hypothesis.',
  provenance: { capabilities_executed: ['fuse_lap_evidence'] },
  follow_ups: [{ label: 'Show evidence against the leading hypothesis', capability_id: 'fuse_lap_evidence', available: true }],
}

function stub(payload: unknown) {
  const fn = vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(payload) } as Response),
  )
  vi.stubGlobal('fetch', fn)
  return fn
}

describe('UniversalQuestion', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => {} })
  })
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('posts the raw question with no question-type selector', async () => {
    const fn = stub({ status: 'PARTIALLY_ANSWERABLE', investigation_id: 'x', duration_ms: 5, compiled: { status: 'PARSED' }, answer: ANSWER, verification: { passed: true, checks_run: 8, violations: [] } })
    render(<UniversalQuestion />)
    fireEvent.change(screen.getByLabelText('Ask RACEWISE anything'), { target: { value: 'Why did Verstappen lose time to Perez on lap 6?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask RACEWISE' }))
    await waitFor(() => expect(fn).toHaveBeenCalled())
    const [url, init] = fn.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/investigations/ask')
    const body = JSON.parse(String(init.body))
    expect(body.question).toContain('Verstappen')
    /* The whole point: the user never selects a question type. */
    expect(body).not.toHaveProperty('question_type')
  })

  it('renders the engine status, the residual and the contradiction verbatim', async () => {
    stub({ status: 'PARTIALLY_ANSWERABLE', investigation_id: 'x', duration_ms: 5, compiled: { status: 'PARSED' }, answer: ANSWER, verification: { passed: true, checks_run: 21, violations: [] } })
    render(<UniversalQuestion />)
    fireEvent.change(screen.getByLabelText('Ask RACEWISE anything'), { target: { value: 'Why did Verstappen lose time?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask RACEWISE' }))
    await screen.findByText('PARTIALLY_ANSWERABLE')
    /* the unexplained remainder is always shown, never dropped */
    expect(screen.getAllByText(/0\.659 s remains unexplained/i).length).toBeGreaterThan(0)
    /* engine states are not renamed or softened */
    expect(screen.getByText('CONTRADICTED_OR_NOT_SUPPORTED')).toBeTruthy()
    /* modelled output keeps its label */
    expect(screen.getByText('MODELLED')).toBeTruthy()
  })

  it('surfaces what could not be established', async () => {
    stub({ status: 'PARTIALLY_ANSWERABLE', investigation_id: 'x', duration_ms: 5, compiled: { status: 'PARSED' }, answer: ANSWER, verification: { passed: true, checks_run: 21, violations: [] } })
    render(<UniversalQuestion />)
    fireEvent.change(screen.getByLabelText('Ask RACEWISE anything'), { target: { value: 'Why did Verstappen lose time?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask RACEWISE' }))
    await screen.findByText('Not established')
    expect(screen.getByText(/unavailable for this session/i)).toBeTruthy()
  })

  it('renders a clarification as a question, not an error', async () => {
    stub({
      status: 'CONTEXT_UNRESOLVED',
      investigation_id: 'x',
      duration_ms: 3,
      compiled: {
        status: 'CONTEXT_UNRESOLVED',
        clarifications: [{ field: 'round', prompt: 'Which race do you mean?', candidates: ['2023 R1 bahrain', '2023 R2 saudi-arabia'] }],
      },
      answer: { ...ANSWER, answer_status: 'CONTEXT_UNRESOLVED', observations: [], spatial: [], hypotheses: [], residuals: [], counterfactuals: [], follow_ups: [] },
      verification: { passed: true, checks_run: 3, violations: [] },
    })
    render(<UniversalQuestion />)
    fireEvent.change(screen.getByLabelText('Ask RACEWISE anything'), { target: { value: 'Why did Verstappen lose time to Perez in 2023?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask RACEWISE' }))
    await screen.findByText('Which race do you mean?')
    expect(screen.getByRole('button', { name: '2023 R1 bahrain' })).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('reports a failed verification rather than hiding it', async () => {
    stub({ status: 'ANSWERABLE', investigation_id: 'x', duration_ms: 4, compiled: { status: 'PARSED' }, answer: ANSWER, verification: { passed: false, checks_run: 21, violations: [{ check: 'phantom_capability' }] } })
    render(<UniversalQuestion />)
    fireEvent.change(screen.getByLabelText('Ask RACEWISE anything'), { target: { value: 'Why?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask RACEWISE' }))
    await screen.findByText('UNVERIFIED')
  })

  it('a follow-up carries the resolved scope forward', async () => {
    const fn = stub({ status: 'PARTIALLY_ANSWERABLE', investigation_id: 'x', duration_ms: 5, compiled: { status: 'PARSED' }, answer: ANSWER, verification: { passed: true, checks_run: 21, violations: [] } })
    render(<UniversalQuestion initialContext={{ driver_a: 'max-verstappen', driver_b: 'sergio-perez' }} />)
    fireEvent.change(screen.getByLabelText('Ask RACEWISE anything'), { target: { value: 'Why did Verstappen lose time?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask RACEWISE' }))
    const follow = await screen.findByLabelText('Follow-up question')
    fireEvent.change(follow, { target: { value: 'Was it sector 2?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    await waitFor(() => expect(fn).toHaveBeenCalledTimes(2))
    const [, init] = fn.mock.calls[1] as unknown as [string, RequestInit]
    const body = JSON.parse(String(init.body))
    expect(body.context).toMatchObject({ driver_a: 'max-verstappen', season: 2023, round: 1 })
  })
})