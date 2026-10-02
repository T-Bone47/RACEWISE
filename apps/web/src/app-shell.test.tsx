/* ============ App shell tests (mission §7 IA, §28 shortcuts) ============
   Navigation groups follow the investigation workflow; every existing route
   survives; the status bar reflects real engine reachability only. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, waitFor } from '@testing-library/react'
import App from './App'
import { mockFetch } from './test-utils'

describe('App shell (workstation IA)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    window.location.hash = ''
    mockFetch({
      '/api/health': { status: 'ok', service: 'racewise' },
      '/api/catalog/sessions?capability=telemetry': {
        total: 99, sessions: [{ season: 2023, round: 1, race_name: 'Bahrain Grand Prix' }],
      },
      '/api/catalog/sessions?page_size=1': { total: 5268, sessions: [] },
    })
  })
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    window.localStorage.clear()
  })

  it('renders the workflow-grouped navigation with every route preserved', async () => {
    const { container } = render(<App />)
    await waitFor(() => {
      expect(container.querySelector('.shell-sidebar')).toBeTruthy()
    })
    const groups = Array.from(container.querySelectorAll('.nav-group-label')).map((g) => g.textContent)
    expect(groups).toEqual(['Investigation', 'Knowledge', 'Analysis', 'Data', 'Workspace'])
    /* all 19 routes reachable from the deck */
    const items = Array.from(container.querySelectorAll('.nav-item .nav-label')).map((i) => i.textContent)
    for (const label of [
      'Command Center', 'Active Investigation', 'Falsification', 'Counterfactual Lab',
      'Investigation Graph', 'Engineering Memory', 'Cross-Race Patterns', 'Pattern Evidence',
      'Lap Comparison', 'Lap Attribution', 'Evidence Fusion', 'Stint Analysis', 'Race Gap',
      'Performance Envelope', 'Regime Timeline',
      'Sessions & Drivers',
      'Autonomous Query', 'Compare', 'Replay',
    ]) {
      expect(items).toContain(label)
    }
  })

  it('the brand carries the product truth', () => {
    const { container } = render(<App />)
    expect(container.querySelector('.shell-header h1')?.textContent).toContain('RACEWISE')
    expect(container.querySelector('.shell-tagline')?.textContent).toContain('evidence-driven race engineering')
  })

  it('the status bar reports real engine reachability, never a static claim', async () => {
    const { container } = render(<App />)
    await waitFor(() => {
      expect(container.querySelector('.shell-statusbar')?.textContent).toContain('ENGINE REACHABLE · DETERMINISTIC CHAIN')
    })
  })

  it('the status bar degrades honestly when the engine is unreachable', async () => {
    cleanup()
    vi.unstubAllGlobals()
    const fn = vi.fn(() => Promise.resolve({
      ok: false, status: 503, json: () => Promise.resolve({}),
    } as Response))
    vi.stubGlobal('fetch', fn)
    const { container } = render(<App />)
    await waitFor(() => {
      expect(container.querySelector('.shell-statusbar')?.textContent).toContain('ENGINE UNREACHABLE')
    })
  })

  it('Ctrl/Cmd+Shift+F toggles analysis focus mode', async () => {
    const { container } = render(<App />)
    await waitFor(() => {
      expect(container.querySelector('.shell-sidebar')).toBeTruthy()
    })
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'F', ctrlKey: true, shiftKey: true, bubbles: true }))
    await waitFor(() => {
      expect(container.querySelector('.shell.zen')).toBeTruthy()
      /* CSS hides the sidebar + status bar in zen mode (display:none) and
         offers an explicit exit affordance */
      expect(container.querySelector('.zen-exit')).toBeTruthy()
    })
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'F', ctrlKey: true, shiftKey: true, bubbles: true }))
    await waitFor(() => {
      expect(container.querySelector('.shell.zen')).toBeNull()
    })
  })

  it('Ctrl/Cmd+K opens the command palette', async () => {
    const { container } = render(<App />)
    await waitFor(() => {
      expect(container.querySelector('.shell-sidebar')).toBeTruthy()
    })
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true }))
    await waitFor(() => {
      expect(container.querySelector('.palette')).toBeTruthy()
    })
    /* Esc closes it */
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    /* palette closes instantly (animated open only — keyboard speed first) */
    await waitFor(() => {
      expect(container.querySelector('.palette')).toBeNull()
    })
  })
})
