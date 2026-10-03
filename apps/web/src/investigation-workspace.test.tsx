/* ============ Investigation Workstation tests (mission §35) ============
   The flagship renders the real 6N payload through the workstation layout:
   header observation band (observed delta + unassigned residual from the
   ledger), measured context strip, stage rail + dominant center canvas,
   persistent decision-trace strip — with honest states everywhere. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import InvestigationView from './InvestigationView'
import { counterfactualPayload, investigationPayload, mockFetch, sessionContextPayload } from './test-utils'

function preset(): URLSearchParams {
  return new URLSearchParams({
    question_type: 'LAP_PERFORMANCE',
    driver_a: 'max-verstappen',
    driver_b: 'sergio-perez',
    season: '2023',
    round: '1',
    lap_number: '6',
  })
}

describe('InvestigationView (Active Investigation workstation)', () => {
  beforeEach(() => {
    mockFetch({
      '/api/catalog/engineering-investigation?': investigationPayload(),
      '/api/catalog/session-context/2023/1': sessionContextPayload(),
      '/api/catalog/counterfactual/2023/1': counterfactualPayload(),
      '/api/catalog/telemetry-comparison/2023/1': {
        verdict: 'PASS',
        window_s: 5,
        top_windows: [
          { t_start_s: 10, speed_delta_kmh: -4, throttle_delta_pct: 1, brake_delta_frac: 0, est_time_loss_s: 0.1 },
        ],
      },
      '/api/catalog/attribution/2023/1': { status: 'VALID_COMPARISON' },
      '/api/catalog/stint-evidence/2023/1': {
        status: 'VALID_COMPARISON',
        stint_metadata: {
          driver_a_stint: { compound: 'hard', lap_range: [14, 57] },
          driver_b_stint: { compound: 'soft', lap_range: [30, 57] },
          laps_selected: 5,
        },
        performance: {
          trend: { status: 'VALID', slope_per_stint_lap: 0.042 },
          mean_delta_s: 0.31, first_delta_s: 0.2, last_delta_s: 0.4,
        },
        residuals: { cumulative_residual_s: 0.12 },
      },
    })
  })
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('auto-runs the investigation for a launcher preset and renders the question', async () => {
    render(<InvestigationView presetParams={preset()} />)
    await waitFor(() => {
      expect(screen.getByText(/lap performance/i)).toBeTruthy()
    })
    expect(screen.getAllByText(/max-verstappen/i).length).toBeGreaterThan(0)
  })

  it('extracts the observed delta and the unassigned residual from the REAL ledger', async () => {
    render(<InvestigationView presetParams={preset()} />)
    await waitFor(() => {
      expect(screen.getByText(/Observed delta \(s\)/i)).toBeTruthy()
    })
    expect(screen.getByText('0.732')).toBeTruthy()
    expect(screen.getByText(/Unassigned residual/i)).toBeTruthy()
    expect(screen.getAllByText(/-0\.659 s/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/UNRESOLVED — never assigned to a mechanism/i)).toBeTruthy()
  })

  it('renders the real comparability verdict in the observation band', async () => {
    render(<InvestigationView presetParams={preset()} />)
    await waitFor(() => {
      expect(screen.getAllByText(/VALID COMPARISON/i).length).toBeGreaterThan(0)
    })
  })

  it('renders the measured context strip with real compounds and positions', async () => {
    render(<InvestigationView presetParams={preset()} />)
    await waitFor(() => {
      expect(screen.getByText('P1')).toBeTruthy()
    })
    expect(screen.getByText(/6L tyre life/i)).toBeTruthy()
  })

  it('renders the stage rail with lifecycle-true stages and real statuses', async () => {
    render(<InvestigationView presetParams={preset()} />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^observation/i })).toBeTruthy()
    })
    expect(screen.getByRole('button', { name: /^hypotheses/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /^evidence/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /^falsification/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /^counterfactual/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /^synthesis/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /^verification/i })).toBeTruthy()
    /* real per-stage status from the payload */
    expect(screen.getByText(/6 evaluated/i)).toBeTruthy()
    expect(screen.getByText(/4 items · 0 conflicts/i)).toBeTruthy()
  })

  it('fetches the aligned traces at the identity fraction with profile samples', async () => {
    const fn = mockFetch({
      '/api/catalog/engineering-investigation?': investigationPayload(),
      '/api/catalog/session-context/2023/1': sessionContextPayload(),
      '/api/catalog/counterfactual/2023/1': counterfactualPayload(),
      '/api/catalog/telemetry-comparison/2023/1': { verdict: 'PASS', window_s: 5, top_windows: [] },
      '/api/catalog/stint-evidence/2023/1': { status: 'UNAVAILABLE' },
    })
    render(<InvestigationView presetParams={preset()} />)
    await waitFor(() => {
      expect(screen.getByTestId('speed-profile-canvas')).toBeTruthy()
    })
    const calls = fn.mock.calls.map((c) => String(c[0])).filter((u) => u.includes('/api/catalog/counterfactual/2023/1'))
    expect(calls.length).toBeGreaterThan(0)
    expect(calls[0]).toContain('fraction=0')
    expect(calls[0]).toContain('include_profile=true')
    expect(calls[0]).toContain('driver=sergio-perez')
    expect(calls[0]).toContain('reference_driver=max-verstappen')
  })

  it('renders the zoomable instrument with controls and the honest grid badge', async () => {
    render(<InvestigationView presetParams={preset()} />)
    await waitFor(() => {
      expect(screen.getByTestId('speed-profile-canvas')).toBeTruthy()
    })
    expect(screen.getByRole('button', { name: 'Zoom in' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Zoom out' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Reset zoom to full lap' })).toBeTruthy()
    expect(screen.getByText('0.25 S ANALYSIS GRID')).toBeTruthy()
  })

  it('renders the degradation context from the real stint evidence', async () => {
    render(<InvestigationView presetParams={preset()} />)
    await waitFor(() => {
      expect(screen.getByText(/Degradation context — measured stint evidence$/i)).toBeTruthy()
    })
    expect(screen.getByText(/\+0\.042 s \/ stint-lap/i)).toBeTruthy()
  })

  it('the Hypotheses stage renders hypothesis rows with canonical states — never ranked', async () => {
    render(<InvestigationView presetParams={preset()} />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^observation/i })).toBeTruthy()
    })
    fireEvent.click(screen.getByRole('button', { name: /^hypotheses/i }))
    await waitFor(() => {
      expect(screen.getByText(/Hypothesis matrix \(never ranked\)/i)).toBeTruthy()
    })
    expect(screen.getAllByText(/H1 Corner Speed/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/H4 Tyre State/i).length).toBeGreaterThan(0)
    /* clicking a hypothesis opens the scientific test in the inspector */
    fireEvent.click(screen.getAllByText(/H2 Throttle/i)[0])
    await waitFor(() => {
      expect(screen.getByRole('complementary', { name: /contextual inspector/i })).toBeTruthy()
    })
    expect(screen.getByText(/Prediction \(engine statement\)/i)).toBeTruthy()
    expect(screen.getAllByText(/Falsification criterion/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/^Result$/i).length).toBeGreaterThan(0)
  })

  it('the Evidence stage renders the ledger with the hypothesis filter', async () => {
    render(<InvestigationView presetParams={preset()} />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^evidence/i })).toBeTruthy()
    })
    fireEvent.click(screen.getByRole('button', { name: /^evidence/i }))
    await waitFor(() => {
      expect(screen.getByText(/Evidence ledger \(4\/4\)/i)).toBeTruthy()
    })
    expect(screen.getByText('evidence_001')).toBeTruthy()
    /* EFFECT column: real supports/contradicts relations from the ledger */
    expect(screen.getByText('\u21ae H1')).toBeTruthy()   /* evidence_006 contradicts H1 */
    expect(screen.getByText('\u2192 H2')).toBeTruthy()   /* evidence_007 supports H2 */
  })

  it('the persistent decision-trace strip is always present and expandable', async () => {
    render(<InvestigationView presetParams={preset()} />)
    await waitFor(() => {
      expect(screen.getByText('TRACE-001')).toBeTruthy()
    })
    fireEvent.click(screen.getByText('TRACE-001'))
    await waitFor(() => {
      expect(screen.getByText(/observed lap delta recorded from canonical facts/i)).toBeTruthy()
    })
    /* basis links to real evidence ids */
    expect(screen.getByText('basis:')).toBeTruthy()
  })

  it('the Synthesis stage renders the engineering report with the conclusion state', async () => {
    render(<InvestigationView presetParams={preset()} />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^synthesis/i })).toBeTruthy()
    })
    fireEvent.click(screen.getByRole('button', { name: /^synthesis/i }))
    await waitFor(() => {
      expect(screen.getByText(/Engineering conclusion — mixed evidence/i)).toBeTruthy()
    })
    expect(screen.getAllByText(/unresolved contradictions block an established explanation/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/Unresolved residual/i)).toBeTruthy()
  })

  it('the Falsification stage renders the honest gate state', async () => {
    render(<InvestigationView presetParams={preset()} />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^falsification/i })).toBeTruthy()
    })
    fireEvent.click(screen.getByRole('button', { name: /^falsification/i }))
    await waitFor(() => {
      expect(screen.getAllByText(/contradictions preserved|contradictions block/i).length).toBeGreaterThan(0)
    })
  })

  it('the Verification stage exposes graph, replay and memory for the scope', async () => {
    render(<InvestigationView presetParams={preset()} />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^verification/i })).toBeTruthy()
    })
    fireEvent.click(screen.getByRole('button', { name: /^verification/i }))
    await waitFor(() => {
      expect(screen.getAllByText(/Engineering graph/i).length).toBeGreaterThan(0)
    })
    expect(screen.getAllByText(/Replay/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Engineering memory/i).length).toBeGreaterThan(0)
  })

  it('renders a structured error state on engine UNAVAILABLE — nothing broadened silently', async () => {
    cleanup()
    vi.unstubAllGlobals()
    mockFetch({
      '/api/catalog/engineering-investigation?': {
        status: 'UNAVAILABLE',
        reason: 'no canonical telemetry ingested for this session (bounded policy)',
      },
    })
    render(<InvestigationView presetParams={preset()} />)
    await waitFor(() => {
      expect(screen.getAllByText(/UNAVAILABLE/i).length).toBeGreaterThan(0)
    })
  })

  it('qualifying scopes are never substituted with race telemetry (honest canvas state)', async () => {
    const fn = mockFetch({
      '/api/catalog/engineering-investigation?': investigationPayload({
        question: { type: 'LAP_PERFORMANCE', scope: { season: 2023, round: 1, driver_a: 'max-verstappen', driver_b: 'sergio-perez', lap_number: 6, stint_number: null, session_type: 'QUALIFYING', pattern_id: null } },
        question_type: 'LAP_PERFORMANCE',
      }),
      '/api/catalog/session-context/2023/1': sessionContextPayload({ session_type: 'QUALIFYING' }),
    })
    render(
      <InvestigationView
        presetParams={new URLSearchParams({
          question_type: 'LAP_PERFORMANCE', driver_a: 'max-verstappen',
          driver_b: 'sergio-perez', season: '2023', round: '1', lap_number: '6',
          session_type: 'QUALIFYING',
        })}
      />,
    )
    await waitFor(() => {
      expect(screen.getByText(/Aligned speed profiles are computed for RACE sessions only/i)).toBeTruthy()
    })
    /* no race-scoped telemetry fetch was made for a qualifying scope */
    const raceFetches = fn.mock.calls.map((c) => String(c[0]))
      .filter((u) => u.includes('/api/catalog/counterfactual/') || u.includes('/api/catalog/telemetry-comparison/'))
    expect(raceFetches.length).toBe(0)
  })
})
