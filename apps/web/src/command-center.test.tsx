/* ============ Command Center view tests ============
   Stitch command-center features mapped to real capabilities: template
   pills that prefill the launcher (real question types only), the real
   6T autonomous console, the recents ledger enriched with real run data,
   and the focused trace preview from the real comparison endpoint. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import CommandCenterView from './CommandCenterView'
import { mockFetch } from './test-utils'

const RECENTS_KEY = 'racewise.recent.investigations.v1'

function seedRecents() {
  window.localStorage.setItem(RECENTS_KEY, JSON.stringify([{
    investigation_id: 'abcd1234abcd1234',
    question_type: 'LAP_PERFORMANCE',
    scope: { season: 2023, round: 1, driver_a: 'max-verstappen', driver_b: 'sergio-perez', lap_number: 6, stint_number: null, session_type: 'RACE', pattern_id: null },
    output_hash: 'hash1',
    conclusion_state: 'MIXED_EVIDENCE',
    evidence_count: 12,
    hypothesis_states: {
      H1_corner_speed: 'CONTRADICTED',
      H2_throttle: 'SUPPORTED',
      H3_braking: 'NOT_SUPPORTED',
      H4_tyre_state: 'NOT_TESTABLE',
      H5_race_control: 'INSUFFICIENT_EVIDENCE',
      H6_drs: 'MIXED_EVIDENCE',
    },
    observed_delta_s: 0.732,
    residual_s: -0.659,
    at: Date.now(),
  }]))
}

describe('CommandCenterView (Stitch Engineering Command Center)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    mockFetch({
      '/api/catalog/sessions?capability=telemetry': {
        total: 99,
        sessions: [{ season: 2023, round: 1, race_name: 'Bahrain Grand Prix' }],
      },
      '/api/catalog/search?q=': { status: 'OK', query: '', result_count: 0, results: [] },
      '/api/catalog/telemetry-comparison/2023/1': {
        verdict: 'PASS',
        top_windows: [
          { t_start_s: 10, speed_delta_kmh: -3, throttle_delta_pct: 0, brake_delta_frac: 0, est_time_loss_s: 0.08 },
          { t_start_s: 24, speed_delta_kmh: -6, throttle_delta_pct: 2, brake_delta_frac: 0, est_time_loss_s: 0.19 },
        ],
      },
    })
  })
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    window.localStorage.clear()
  })

  it('renders the question-first hero with templates for the real question types (§26)', () => {
    render(<CommandCenterView onNavigated={() => undefined} />)
    for (const label of [
      'Lap performance', 'Stint performance', 'Race gap', 'Performance regimes',
      'Cross-race pattern', 'Hypothesis evaluation', 'Counterfactual eligibility',
      'Qualifying lap (2018+)',
    ]) {
      expect(screen.getByText(label)).toBeTruthy()
    }
  })

  it('a template pill prefills the launcher with the real question type', () => {
    render(<CommandCenterView onNavigated={() => undefined} />)
    fireEvent.click(screen.getByText('Race gap'))
    const select = screen.getAllByLabelText(/question type:/i)[0] as HTMLSelectElement
    expect(select.value).toBe('RACE_GAP')
  })

  it('the autonomous console POSTs the question to the real 6T endpoint', async () => {
    const fn = mockFetch({
      '/api/catalog/sessions?capability=telemetry': {
        total: 1, sessions: [{ season: 2023, round: 1, race_name: 'Bahrain Grand Prix' }],
      },
      '/api/investigations/autonomous': {
        run_id: 'run_123', status: 'COMPLETED', question: 'q',
        stage_ledger: [{ stage: 'QUESTION_PARSED', status: 'COMPLETED' }],
        tool_calls_consumed: 12,
        engine_result_ref: { status: 'VALID', investigation_id: 'abcd1234abcd1234', output_hash: 'h' },
      },
    })
    render(<CommandCenterView onNavigated={() => undefined} />)
    const input = screen.getByLabelText(/Engineering question/i)
    fireEvent.change(input, { target: { value: 'Why did the gap open in Bahrain 2023?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Investigate' }))
    await waitFor(() => {
      const calls = fn.mock.calls.filter((c) => String(c[0]).includes('/api/investigations/autonomous'))
      expect(calls.length).toBe(1)
      expect(String(calls[0][1]?.method)).toBe('POST')
    })
    await waitFor(() => {
      expect(screen.getByText(/run run_123/)).toBeTruthy()
      expect(screen.getByText(/12 tool calls/i)).toBeTruthy()
    })
  })

  it('the autonomous console surfaces a real 422 with the supported question types', async () => {
    vi.unstubAllGlobals()
    const fn = vi.fn(() => Promise.resolve({
      ok: false,
      status: 422,
      json: () => Promise.resolve({
        detail: 'UNSUPPORTED_QUESTION — supported_question_types: LAP_PERFORMANCE, STINT_PERFORMANCE, RACE_GAP, PERFORMANCE_REGIME, CROSS_RACE_PATTERN, HYPOTHESIS_EVALUATION, COUNTERFACTUAL_ELIGIBILITY',
      }),
    } as Response))
    vi.stubGlobal('fetch', fn)
    render(<CommandCenterView onNavigated={() => undefined} />)
    fireEvent.change(screen.getByLabelText(/Engineering question/i), { target: { value: 'What is the meaning of life?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Investigate' }))
    await waitFor(() => {
      expect(screen.getByText(/UNSUPPORTED_QUESTION/i)).toBeTruthy()
    })
  })

  it('renders real recents with conclusion state, measured delta, residual and hypothesis states', () => {
    seedRecents()
    render(<CommandCenterView onNavigated={() => undefined} />)
    expect(screen.getByText(/MIXED EVIDENCE/i)).toBeTruthy()
    expect(screen.getByText(/Δ 0\.732 s/i)).toBeTruthy()
    expect(screen.getByText(/residual -0\.659 s/i)).toBeTruthy()
    /* one dot per canonical hypothesis, colored by real state */
    const dots = screen.getAllByTitle(/H[1-6]_.*: (CONTRADICTED|SUPPORTED|NOT_SUPPORTED|NOT_TESTABLE|INSUFFICIENT_EVIDENCE|MIXED_EVIDENCE)/)
    expect(dots.length).toBe(6)
  })

  it('focusing a recent loads the real comparison windows for the trace preview', async () => {
    seedRecents()
    render(<CommandCenterView onNavigated={() => undefined} />)
    /* the measured delta chip is unique to the seeded recent row */
    fireEvent.click(screen.getByText(/Δ 0\.732 s/i))
    await waitFor(() => {
      expect(screen.getByText(/Focused trace preview/i)).toBeTruthy()
    })
    /* the real window bars render (one per window in the mocked payload) */
    const bars = document.querySelectorAll('.focus-bar')
    expect(bars.length).toBe(2)
  })

  it('shows the real system status from the catalog — no fabricated counts', async () => {
    render(<CommandCenterView onNavigated={() => undefined} />)
    await waitFor(() => {
      expect(screen.getByText(/99 catalog sessions with telemetry capability/i)).toBeTruthy()
    })
    /* fabricated Stitch strings must never appear */
    expect(screen.queryByText(/42k slices/i)).toBeNull()
    expect(screen.queryByText(/1,420 solved/i)).toBeNull()
    expect(screen.queryByText(/99\.8%/)).toBeNull()
  })
})
