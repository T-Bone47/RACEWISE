/* ============ Stitch integration component tests ============
   The context strip, the telemetry canvas and the degradation panel render
   only real API payloads with honest unavailable states. */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { ContextStrip, ComparabilityChip, SpeedProfileCanvas } from './stitch'
import type { ProfileSamples } from './types'
import { mockFetch, sessionContextPayload } from './test-utils'

describe('ContextStrip (measured session context)', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('renders real compounds, tyre life and positions at the investigated lap', async () => {
    mockFetch({
      '/api/catalog/session-context/2023/1': sessionContextPayload(),
    })
    render(
      <ContextStrip
        season={2023} round={1} sessionType="RACE"
        driverA="max-verstappen" driverB="sergio-perez" lap={6} stint={null}
      />,
    )
    await waitFor(() => {
      expect(screen.getByText('P1')).toBeTruthy()
      expect(screen.getByText('P2')).toBeTruthy()
    })
    /* VER on lap 6 is on stint 1 (lap_start 14)? lap 6 < 14 -> compound from lap facts */
    expect(screen.getByText(/6L tyre life/i)).toBeTruthy()
  })

  it('renders the measured weather summary — never an invented temperature', async () => {
    mockFetch({
      '/api/catalog/session-context/2023/1': sessionContextPayload(),
    })
    render(
      <ContextStrip
        season={2023} round={1} sessionType="RACE"
        driverA="max-verstappen" driverB="sergio-perez" lap={6} stint={null}
      />,
    )
    await waitFor(() => {
      expect(screen.getByText(/22\.1→21\.4°C/i)).toBeTruthy()
      expect(screen.getByText(/30\.2→29\.1°C/i)).toBeTruthy()
    })
  })

  it('renders an honest unavailable weather chip when nothing is recorded', async () => {
    mockFetch({
      '/api/catalog/session-context/2023/1': sessionContextPayload({
        weather: { status: 'UNAVAILABLE', reason: 'no canonical weather observations for this session' },
      }),
    })
    render(
      <ContextStrip
        season={2023} round={1} sessionType="RACE"
        driverA="max-verstappen" driverB="sergio-perez" lap={6} stint={null}
      />,
    )
    await waitFor(() => {
      expect(screen.getByText(/weather not recorded/i)).toBeTruthy()
    })
  })

  it('renders honest telemetry coverage (0.25 s grid) — never a native-rate claim', async () => {
    mockFetch({
      '/api/catalog/session-context/2023/1': sessionContextPayload(),
    })
    render(
      <ContextStrip
        season={2023} round={1} sessionType="RACE"
        driverA="max-verstappen" driverB="sergio-perez" lap={6} stint={null}
      />,
    )
    await waitFor(() => {
      expect(screen.getByText(/5 covered laps · 0\.25s grid/i)).toBeTruthy()
    })
  })

  it('renders an honest "not in canonical rows" chip for an unknown driver', async () => {
    mockFetch({
      '/api/catalog/session-context/2023/1': sessionContextPayload(),
    })
    render(
      <ContextStrip
        season={2023} round={1} sessionType="RACE"
        driverA="unknown-driver-x" driverB="sergio-perez" lap={6} stint={null}
      />,
    )
    await waitFor(() => {
      expect(screen.getByText(/lap context not in canonical rows/i)).toBeTruthy()
    })
  })
})

describe('ComparabilityChip (real 6E verdict)', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('renders the real 6E attribution status for the scope', async () => {
    mockFetch({
      '/api/catalog/attribution/2023/1': { status: 'VALID_COMPARISON' },
    })
    render(
      <ComparabilityChip
        season={2023} round={1} driverA="max-verstappen" driverB="sergio-perez"
        lap={6} sessionType="RACE"
      />,
    )
    await waitFor(() => {
      expect(screen.getByText(/VALID COMPARISON/i)).toBeTruthy()
    })
  })

  it('renders the honest 6E failure status — never a synthetic VALID', async () => {
    mockFetch({
      '/api/catalog/attribution/2023/1': {
        status: 'INSUFFICIENT_EVIDENCE', reason: 'no telemetry coverage for this lap',
      },
    })
    render(
      <ComparabilityChip
        season={2023} round={1} driverA="max-verstappen" driverB="sergio-perez"
        lap={6} sessionType="RACE"
      />,
    )
    await waitFor(() => {
      expect(screen.getByText(/INSUFFICIENT EVIDENCE/i)).toBeTruthy()
      expect(screen.getByText(/no telemetry coverage for this lap/i)).toBeTruthy()
    })
  })

  it('renders nothing for out-of-scope questions (no lap, qualifying)', () => {
    const { container } = render(
      <ComparabilityChip
        season={2023} round={1} driverA="max-verstappen" driverB="sergio-perez"
        lap={null} sessionType="RACE"
      />,
    )
    expect(container.querySelectorAll('[role="listitem"]').length).toBe(0)
  })
})

const SAMPLES: ProfileSamples = {
  n_total_points: 300, n_samples: 8, cap: 192, unit: 'km/h',
  sampling: 'deterministic evenly spaced decimation',
  t_s: [0, 5, 10, 15, 20, 25, 30, 35],
  target_kmh: [300, 120, 280, 90, 300, 130, 260, 310],
  reference_kmh: [305, 125, 282, 95, 302, 135, 262, 312],
  counterfactual_kmh: [302, 122, 281, 92, 301, 132, 261, 311],
}

describe('SpeedProfileCanvas (real aligned traces)', () => {
  it('renders the traces, the honest grid badge and the decimation note', () => {
    render(
      <SpeedProfileCanvas
        samples={SAMPLES}
        targetLabel="sergio-perez (target)"
        referenceLabel="max-verstappen (reference)"
      />,
    )
    expect(screen.getByText(/0\.25 S ANALYSIS GRID/i)).toBeTruthy()
    expect(screen.getByText(/8 OF 300 POINTS/i)).toBeTruthy()
    expect(screen.getByText(/sergio-perez \(target\)/i)).toBeTruthy()
    expect(screen.getByText(/max-verstappen \(reference\)/i)).toBeTruthy()
  })

  it('renders an honest empty state when no samples exist', () => {
    render(
      <SpeedProfileCanvas
        samples={null}
        targetLabel="a"
        referenceLabel="b"
        emptyReason="UNAVAILABLE — no canonical telemetry ingested for this session"
      />,
    )
    expect(screen.getByText(/UNAVAILABLE — no canonical telemetry ingested/i)).toBeTruthy()
  })

  it('shows the counterfactual trace with a MODELLED label when requested', () => {
    render(
      <SpeedProfileCanvas
        samples={SAMPLES}
        targetLabel="baseline"
        referenceLabel="reference"
        showCounterfactual
        counterfactualLabel="counterfactual"
      />,
    )
    expect(screen.getByText(/counterfactual.*MODELLED/i)).toBeTruthy()
  })
})
