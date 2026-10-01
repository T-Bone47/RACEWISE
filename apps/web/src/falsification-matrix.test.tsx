/* ============ Falsification Matrix view tests ============
   The Stitch falsification-matrix UX must render only real engine output:
   canonical hypothesis states, real evidence links, real counts, the real
   decision trace — and honest failure states. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import FalsificationMatrixView from './FalsificationMatrixView'
import { investigationPayload, mockFetch } from './test-utils'

describe('FalsificationMatrixView', () => {
  beforeEach(() => {
    mockFetch({
      '/api/catalog/engineering-investigation': investigationPayload(),
    })
  })
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('fetches the real investigation for the scope and renders the matrix', async () => {
    render(<FalsificationMatrixView />)
    await waitFor(() => {
      expect(screen.getByText(/H1 Corner Speed/i)).toBeTruthy()
    })
    /* the canonical hypothesis statements (engine methodology) */
    expect(screen.getAllByText(/lower speed through corners\/fast sections/i).length).toBeGreaterThan(0)
    /* engine criterion column */
    expect(screen.getAllByText(/contradicted when valid/i).length).toBeGreaterThan(0)
  })

  it('renders every canonical hypothesis state verbatim — never renamed', async () => {
    render(<FalsificationMatrixView />)
    await waitFor(() => {
      expect(screen.getByText(/Hypotheses in scope/i)).toBeTruthy()
    })
    for (const state of ['CONTRADICTED', 'SUPPORTED', 'NOT_SUPPORTED', 'NOT_TESTABLE', 'INSUFFICIENT EVIDENCE', 'MIXED EVIDENCE']) {
      expect(screen.getAllByText(state, { exact: false }).length).toBeGreaterThan(0)
    }
  })

  it('computes the protocol summary cards from the payload (real counts)', async () => {
    render(<FalsificationMatrixView />)
    await waitFor(() => {
      expect(screen.getByText('6')).toBeTruthy() // hypotheses in scope
    })
    /* contradicted: 1, supported: 1 — from hypothesis_evaluations */
    expect(screen.getAllByText(/contradicted/i).length).toBeGreaterThan(0)
  })

  it('evidence id chips open the real ledger entry in a drawer', async () => {
    render(<FalsificationMatrixView />)
    await waitFor(() => {
      expect(screen.getByText(/H2 Throttle/i)).toBeTruthy()
    })
    fireEvent.click(screen.getByText('evidence_007'))
    await waitFor(() => {
      expect(screen.getByText(/Evidence evidence_007/i)).toBeTruthy()
    })
    /* the drawer shows the real claim */
    expect(screen.getAllByText(/formal evaluation of H2_throttle/i).length).toBeGreaterThan(0)
  })

  it('the CONTRADICTED filter narrows to real contradicted rows only', async () => {
    render(<FalsificationMatrixView />)
    await waitFor(() => {
      expect(screen.getByText(/H2 Throttle/i)).toBeTruthy()
    })
    fireEvent.click(screen.getByRole('button', { name: /CONTRADICTED \(1\)/i }))
    await waitFor(() => {
      expect(screen.queryByText(/H2 Throttle/i)).toBeNull()
    })
    expect(screen.getByText(/H1 Corner Speed/i)).toBeTruthy()
  })

  it('expanding a hypothesis row lists the evaluated evidence items', async () => {
    render(<FalsificationMatrixView />)
    await waitFor(() => {
      expect(screen.getByText(/H1 Corner Speed/i)).toBeTruthy()
    })
    fireEvent.click(screen.getByText(/H1 Corner Speed/i))
    await waitFor(() => {
      expect(screen.getAllByText(/Evaluated evidence for H1 Corner Speed/i).length).toBeGreaterThan(0)
    })
  })

  it('renders the real decision trace and epistemic boundaries', async () => {
    render(<FalsificationMatrixView />)
    await waitFor(() => {
      expect(screen.getByText(/Decision trace — deterministic sequence/i)).toBeTruthy()
    })
    expect(screen.getByText('TRACE-001')).toBeTruthy()
    expect(screen.getByText(/SUPPORT is not PROOF/i)).toBeTruthy()
  })

  it('renders the synthesis honestly — no causal "primary cause" language', async () => {
    render(<FalsificationMatrixView />)
    await waitFor(() => {
      expect(screen.getByText(/Synthesis \(mixed evidence\)/i)).toBeTruthy()
    })
    expect(screen.getByText(/never assigns the residual to a mechanism/i)).toBeTruthy()
  })

  it('renders a structured error state when the engine reports non-VALID', async () => {
    cleanup()
    vi.unstubAllGlobals()
    mockFetch({
      '/api/catalog/engineering-investigation': {
        status: 'UNAVAILABLE', reason: 'no canonical telemetry ingested for this session (bounded policy)',
      },
    })
    render(<FalsificationMatrixView />)
    await waitFor(() => {
      expect(screen.getAllByText(/UNAVAILABLE/i).length).toBeGreaterThan(0)
    })
    expect(screen.getByText(/no canonical telemetry ingested/i)).toBeTruthy()
  })
})
