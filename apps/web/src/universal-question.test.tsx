/* ============ universal question panel tests ============
   The panel's job is to render engine truth without embellishing it. These
   tests pin the properties that matter epistemically: statuses are shown
   verbatim, residuals are never hidden, counterfactuals keep their MODELLED
   label, and a clarification question is rendered as a question rather than an
   error. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

/* ============ engineering autopsy + decision twin (§26, §40) ============
   Two properties are worth more than any pixel here:

   1. A measurement event must never read as a performance change. The panel
      hides them by default and shows them only on request, because 46
      telemetry-availability flips would bury the 7 regime changes an engineer
      actually came to read.
   2. A modelled scenario must never read as a prediction. Every row carries
      MODELLED, and a refusal is rendered as a refusal with its reason. */

const EVENT_ANSWER = {
  ...ANSWER,
  scope: { season: 2023, round: 1, driver_a: 'max-verstappen', driver_b: 'sergio-perez', lap_number: 6 },
  events: [
    {
      event_id: 'EV-004-aaa', event_type: 'REGIME_CHANGE', lap_start: 4,
      observed_change: 'performance regime changed from NARROWING to STABLE',
      magnitude: 0.0222, unit: 's/lap', materiality: 'ENGINEERING',
      source_capability: 'analyze_performance_regimes',
      method: 'OLS slope segmentation', limitations: [],
    },
    {
      event_id: 'EV-014-bbb', event_type: 'UNMEASURED_INTERVAL', lap_start: 14,
      observed_change: 'lap not comparable: is_pit_in_lap',
      magnitude: null, unit: null, materiality: 'MEASUREMENT',
      source_capability: 'analyze_performance_regimes', method: null,
      limitations: ['This is a change in measurement availability, not a change in performance.'],
    },
  ],
  counter_evidence: [
    { hypothesis_id: 'H1_corner_speed', evidence_id: 'ev_brake', statement: 'brake point was later, not earlier', resolved: true },
  ],
}

const TWIN_OK = {
  status: 'COMPLETED',
  dimension: 'speed',
  intervention_type: 'REMOVE_DEFICIT',
  scenario_space: [
    { fraction: 0.0, status: 'COMPLETED', delta_lap_time_s: 0.0, claim_class: 'MODELLED', is_historical_truth: false, validity: 'ALL_GATES_PASS' },
    { fraction: 1.0, status: 'COMPLETED', delta_lap_time_s: -1.98, claim_class: 'MODELLED', is_historical_truth: false, validity: 'ALL_GATES_PASS' },
  ],
  sensitivity: { shape: 'MONOTONIC', note: 'It is not evidence of physical causation.' },
  baseline: { claim_class: 'OBSERVED', lap_time_s: 93.214, source: 'measured canonical lap' },
  limitations: ['Single-lap telemetry intervention sensitivity.'],
}

const TWIN_REFUSED = {
  status: 'UNSUPPORTED',
  dimension: 'brake',
  intervention_type: 'REMOVE_DEFICIT',
  reason: "'brake' has no deterministic lap-time model; modelled signals: ['speed']",
  scenario_space: [],
  sensitivity: { shape: 'UNSUPPORTED', note: '' },
  baseline: { claim_class: 'OBSERVED', lap_time_s: null, source: 'unavailable' },
  limitations: ['No physical model exists for this dimension.'],
}

function stubTwin(twin: unknown, answer: unknown = EVENT_ANSWER) {
  const fn = vi.fn((url: string) => {
    if (String(url).includes('decision-twin')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(twin) } as Response)
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({
        status: 'PARTIALLY_ANSWERABLE', investigation_id: 'x', duration_ms: 5,
        compiled: { status: 'PARSED' }, answer,
        verification: { passed: true, checks_run: 21, violations: [] },
      }),
    } as Response)
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

async function askOnce() {
  fireEvent.change(screen.getByLabelText('Ask RACEWISE anything'), { target: { value: 'What materially changed in this race?' } })
  fireEvent.click(screen.getByRole('button', { name: 'Ask RACEWISE' }))
  await screen.findByText('PARTIALLY_ANSWERABLE')
}

describe('UniversalQuestion autopsy timeline', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => {} })
  })
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('shows engineering events with the capability that produced them', async () => {
    stubTwin(TWIN_OK)
    render(<UniversalQuestion />)
    await askOnce()
    expect(screen.getByText(/performance regime changed from NARROWING to STABLE/)).toBeTruthy()
    /* the source is never hidden: an event without provenance is a rumour */
    expect(screen.getByText(/analyze_performance_regimes/)).toBeTruthy()
  })

  it('hides measurement events until the user asks for them', async () => {
    stubTwin(TWIN_OK)
    render(<UniversalQuestion />)
    await askOnce()
    /* the pit-lap measurement artefact is not presented as a change... */
    expect(screen.queryByText(/lap not comparable/)).toBeNull()
    const toggle = screen.getByRole('button', { name: 'Show measurement events' })
    expect(toggle).toBeTruthy()
    /* ...but it is one click away, and then it is clearly labelled */
    fireEvent.click(toggle)
    expect(screen.getByText(/lap not comparable/)).toBeTruthy()
    expect(screen.getAllByText('MEASUREMENT').length).toBeGreaterThan(0)
  })

  it('names the disconfirming evidence rather than only its id', async () => {
    stubTwin(TWIN_OK)
    render(<UniversalQuestion />)
    await askOnce()
    expect(screen.getByText(/brake point was later, not earlier/)).toBeTruthy()
  })
})

describe('UniversalQuestion what-if sweep', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => {} })
  })
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('labels every scenario MODELLED and never as a prediction', async () => {
    const fn = stubTwin(TWIN_OK)
    render(<UniversalQuestion />)
    await askOnce()
    fireEvent.click(screen.getByRole('button', { name: 'Run scenario sweep' }))
    await screen.findByText(/Modelled effect of removing speed/)
    /* the caption states it is not a prediction */
    expect(screen.getByText(/not a prediction/)).toBeTruthy()
    /* every row carries the claim class. Scoped to the sweep table so the
       answer's own counterfactual chip cannot inflate the count. */
    const table = screen.getByRole('table')
    expect(within(table).getAllByText('MODELLED').length).toBe(
      TWIN_OK.scenario_space.length,
    )
    /* the baseline is a measurement, and is labelled as one */
    expect(screen.getByText(/93\.214 s/)).toBeTruthy()
    expect(screen.getByText('OBSERVED')).toBeTruthy()
    /* the sweep posts the resolved scope, never a guessed lap */
    const twinCall = fn.mock.calls.find((c) => String(c[0]).includes('decision-twin'))
    expect(twinCall).toBeTruthy()
    const body = JSON.parse(String((twinCall as unknown as [string, RequestInit])[1].body))
    expect(body.lap_number).toBe(6)
    expect(body.driver).toBe('max-verstappen')
  })

  it('renders a refusal as a refusal, with the reason', async () => {
    stubTwin(TWIN_REFUSED)
    render(<UniversalQuestion />)
    await askOnce()
    fireEvent.click(screen.getByRole('button', { name: 'Run scenario sweep' }))
    await screen.findByText('UNSUPPORTED')
    expect(screen.getByText(/no deterministic lap-time model/)).toBeTruthy()
    /* nothing was invented to fill the empty sweep: no scenario table at all */
    expect(screen.queryByRole('table')).toBeNull()
    expect(within(screen.getByLabelText('What if scenario sweep')).queryByText('MODELLED')).toBeNull()
  })

  it('offers no sweep when the question pinned no lap', async () => {
    /* lap_number deliberately absent, as a race-wide investigation leaves it */
    const fn = stubTwin(TWIN_OK, {
      ...EVENT_ANSWER,
      scope: { season: 2023, round: 1, driver_a: 'max-verstappen', driver_b: 'sergio-perez' },
    })
    render(<UniversalQuestion initialContext={{ season: 2023, round: 1 }} />)
    await askOnce()
    expect(screen.queryByRole('button', { name: 'Run scenario sweep' })).toBeNull()
    expect(screen.getByText(/needs a pinned lap/)).toBeTruthy()
    /* and it did not guess one */
    expect(fn.mock.calls.some((c) => String(c[0]).includes('decision-twin'))).toBe(false)
  })
})
