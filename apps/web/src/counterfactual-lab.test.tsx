/* ============ Counterfactual Lab view tests ============
   The lab renders only real engine output: MODELLED labels on every
   modelled quantity, the real validation gates, the real aligned profile
   samples and the real Phase 6J sweep. Unavailable scopes render honest
   states — never a synthetic trace or an invented sensitivity curve. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import CounterfactualView from './CounterfactualView'
import { counterfactualPayload, envelopePayload, mockFetch } from './test-utils'

describe('CounterfactualView (Stitch Counterfactual Lab)', () => {
  beforeEach(() => {
    mockFetch({
      '/api/catalog/sessions?capability=telemetry': {
        total: 1,
        sessions: [{ season: 2023, round: 1, race_name: 'Bahrain Grand Prix' }],
      },
      '/api/catalog/counterfactual/2023/1': counterfactualPayload(),
      '/api/catalog/performance-envelope/2023/1': envelopePayload(),
    })
  })
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('labels every modelled quantity MODELLED — NOT HISTORIAL (mandatory §11)', async () => {
    render(<CounterfactualView />)
    fireEvent.click(screen.getByRole('button', { name: /run counterfactual/i }))
    await waitFor(() => {
      expect(screen.getByText(/MODELLED · NOT HISTORICAL/i)).toBeTruthy()
    })
    /* the epistemics paragraph is the engine's own sentence */
    expect(screen.getByText(/not a historical fact, not a prediction, not a causal proof/i)).toBeTruthy()
  })

  it('renders the KPI ribbons from real payload fields', async () => {
    render(<CounterfactualView />)
    fireEvent.click(screen.getByRole('button', { name: /run counterfactual/i }))
    await waitFor(() => {
      expect(screen.getByText(/93\.800 s/i)).toBeTruthy() /* baseline modeled_lap_time_s */
    })
    expect(screen.getByText(/93\.650 s/i)).toBeTruthy()  /* counterfactual modeled_lap_time_s */
    expect(screen.getAllByText(/-0\.150 s/i).length).toBeGreaterThan(0) /* modelled delta */
    expect(screen.getByText(/6 \/ 6 PASS/i)).toBeTruthy() /* gates pass count */
  })

  it('renders the real validation gates with the engine detail', async () => {
    render(<CounterfactualView />)
    fireEvent.click(screen.getByRole('button', { name: /run counterfactual/i }))
    await waitFor(() => {
      expect(screen.getByText(/baseline_reproduction/i)).toBeTruthy()
    })
    expect(screen.getByText(/speed has a deterministic lap-time model/i)).toBeTruthy()
  })

  it('renders the aligned speed profile canvas from real samples', async () => {
    render(<CounterfactualView />)
    fireEvent.click(screen.getByRole('button', { name: /run counterfactual/i }))
    await waitFor(() => {
      expect(screen.getByTestId('speed-profile-canvas')).toBeTruthy()
    })
    /* honest grid labeling — never a native-rate claim */
    expect(screen.getByText(/0\.25 S ANALYSIS GRID/i)).toBeTruthy()
    expect(screen.getByText(/deterministic decimation, display only/i)).toBeTruthy()
  })

  it('renders the real 6J sensitivity sweep and its classification', async () => {
    render(<CounterfactualView />)
    fireEvent.click(screen.getByRole('button', { name: /run counterfactual/i }))
    await waitFor(() => {
      expect(screen.getByText(/Model sensitivity sweep — bounded scenarios \(Phase 6J\)/i)).toBeTruthy()
    })
    /* real sweep point values from the mocked envelope payload */
    expect(screen.getByText(/93\.720000/)).toBeTruthy()
    expect(screen.getByText(/NON_LINEAR/i)).toBeTruthy()
    expect(screen.getByText(/never a causal effect and never a historical result/i)).toBeTruthy()
  })

  it('shows the engine method — no fabricated solver branding', async () => {
    render(<CounterfactualView />)
    fireEvent.click(screen.getByRole('button', { name: /run counterfactual/i }))
    await waitFor(() => {
      expect(screen.getByText(/fixed-distance segment integration/i)).toBeTruthy()
    })
    /* the fabricated Stitch solver must never appear */
    expect(screen.queryByText(/AeroDelta/i)).toBeNull()
    expect(screen.queryByText(/8-CORE/i)).toBeNull()
  })

  it('renders an honest unavailable state — never a synthetic trace', async () => {
    cleanup()
    vi.unstubAllGlobals()
    mockFetch({
      '/api/catalog/sessions?capability=telemetry': {
        total: 1, sessions: [{ season: 2023, round: 1, race_name: 'Bahrain Grand Prix' }],
      },
      '/api/catalog/counterfactual/2023/1': {
        status: 'UNAVAILABLE',
        reason: 'no canonical telemetry ingested for this session (bounded policy)',
      },
    })
    render(<CounterfactualView />)
    fireEvent.click(screen.getByRole('button', { name: /run counterfactual/i }))
    await waitFor(() => {
      expect(screen.getByText(/no canonical telemetry ingested for this session/i)).toBeTruthy()
    })
    expect(screen.queryByTestId('speed-profile-canvas')).toBeNull()
  })

  it('carries the real provenance and output hash', async () => {
    render(<CounterfactualView />)
    fireEvent.click(screen.getByRole('button', { name: /run counterfactual/i }))
    await waitFor(() => {
      expect(screen.getByText(/output hash beefbeefbeefbeef/i)).toBeTruthy()
    })
    expect(screen.getByText(/loss_attribution\.ALPHA_RESAMPLE grid \(0\.25 s\)/i)).toBeTruthy()
  })
})
