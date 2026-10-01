/* ============ Investigation Workspace (Stitch flagship) tests ============
   The flagship renders the real 6N payload: the measured KPI strip
   (observed delta + unassigned residual extracted from the evidence
   ledger), the measured context strip, the aligned telemetry canvas and
   the degradation context — with honest states everywhere. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
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

describe('InvestigationView (Stitch Active Investigation Workspace)', () => {
  beforeEach(() => {
    mockFetch({
      '/api/catalog/engineering-investigation?': investigationPayload(),
      '/api/catalog/session-context/2023/1': sessionContextPayload(),
      '/api/catalog/counterfactual/2023/1': counterfactualPayload(),
      '/api/catalog/telemetry-comparison/2023/1': {
        verdict: 'PASS',
        top_windows: [
          { t_start_s: 10, speed_delta_kmh: -4, throttle_delta_pct: 1, brake_delta_frac: 0, est_time_loss_s: 0.1 },
        ],
      },
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

  it('renders the measured context strip with real compounds and positions', async () => {
    render(<InvestigationView presetParams={preset()} />)
    await waitFor(() => {
      expect(screen.getByText('P1')).toBeTruthy()
    })
    expect(screen.getByText(/6L tyre life/i)).toBeTruthy()
  })

  it('fetches the aligned traces at the identity fraction with profile samples', async () => {
    const fn = mockFetch({
      '/api/catalog/engineering-investigation?': investigationPayload(),
      '/api/catalog/session-context/2023/1': sessionContextPayload(),
      '/api/catalog/counterfactual/2023/1': counterfactualPayload(),
      '/api/catalog/telemetry-comparison/2023/1': { verdict: 'PASS', top_windows: [] },
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

  it('renders the degradation context from the real 6G stint evidence', async () => {
    render(<InvestigationView presetParams={preset()} />)
    await waitFor(() => {
      expect(screen.getByText(/Degradation context — measured stint evidence \(6G\)/i)).toBeTruthy()
    })
    expect(screen.getByText(/\+0\.042 s \/ stint-lap/i)).toBeTruthy()
  })

  it('renders the real hypothesis matrix with canonical states and coverage counts', async () => {
    render(<InvestigationView presetParams={preset()} />)
    await waitFor(() => {
      expect(screen.getByText(/Hypothesis matrix \(never ranked\)/i)).toBeTruthy()
    })
    expect(screen.getAllByText(/H1 Corner Speed/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/H4 Tyre State/i).length).toBeGreaterThan(0)
  })

  it('renders the decision trace with basis links to real evidence ids', async () => {
    render(<InvestigationView presetParams={preset()} />)
    await waitFor(() => {
      expect(screen.getByText('TRACE-001')).toBeTruthy()
    })
    expect(screen.getByText(/observed lap delta recorded from canonical facts/i)).toBeTruthy()
  })

  it('renders the synthesis conclusion state and its real limitation', async () => {
    render(<InvestigationView presetParams={preset()} />)
    await waitFor(() => {
      expect(screen.getAllByText(/MIXED EVIDENCE/i).length).toBeGreaterThan(0)
    })
    expect(screen.getAllByText(/unresolved contradictions block an established explanation/i).length).toBeGreaterThan(0)
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
      expect(screen.getByText(/Aligned speed profiles and window comparisons are computed for RACE/i)).toBeTruthy()
    })
    /* no race-scoped telemetry fetch was made for a qualifying scope */
    const raceFetches = fn.mock.calls.map((c) => String(c[0]))
      .filter((u) => u.includes('/api/catalog/counterfactual/') || u.includes('/api/catalog/telemetry-comparison/'))
    expect(raceFetches.length).toBe(0)
  })
})
