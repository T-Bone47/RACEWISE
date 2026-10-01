/* ============ Command palette tests (mission §22, audit §7) ============
   Only real actions: grouped navigation commands, structured search, and
   context actions built from the current route scope. Keyboard selection
   must reach EVERY entry — commands and search results alike. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import CommandPalette from './CommandPalette'
import { mockFetch } from './test-utils'

describe('CommandPalette', () => {
  beforeEach(() => {
    mockFetch({
      '/api/catalog/search?q=': {
        status: 'OK', query: 'verstappen', result_count: 1,
        results: [{
          result_type: 'DRIVER', label: 'max-verstappen', detail: 'driver',
          ref: { driver_key: 'max-verstappen' },
          provenance: { matched_on: 'driver_key', match_mode: 'exact' },
        }],
      },
    })
  })
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('renders grouped real commands', () => {
    render(<CommandPalette onClose={() => undefined} onNavigate={() => undefined} currentView="command" />)
    expect(screen.getByText('Investigation')).toBeTruthy()
    expect(screen.getByText('Knowledge')).toBeTruthy()
    expect(screen.getByText('Analysis')).toBeTruthy()
    expect(screen.getByText('Data & workspace')).toBeTruthy()
    expect(screen.getByText('New investigation')).toBeTruthy()
    expect(screen.getByText('Open engineering memory')).toBeTruthy()
  })

  it('filters commands as you type', () => {
    render(<CommandPalette onClose={() => undefined} onNavigate={() => undefined} currentView="command" />)
    fireEvent.change(screen.getByLabelText(/Command search/i), { target: { value: 'memory' } })
    expect(screen.getByText('Open engineering memory')).toBeTruthy()
    expect(screen.queryByText('New investigation')).toBeNull()
  })

  it('keyboard ArrowDown can reach typed search results (audit fix)', async () => {
    const nav = vi.fn()
    render(<CommandPalette onClose={() => undefined} onNavigate={nav} currentView="command" />)
    const input = screen.getByLabelText(/Command search/i)
    fireEvent.change(input, { target: { value: 'verstappen' } })
    await waitFor(() => {
      expect(screen.getByText('max-verstappen')).toBeTruthy()
    })
    /* move all the way down: commands were filtered out by the query, so the
       first entry is the search result; ArrowDown then Enter must run it */
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => {
      expect(nav.mock.calls.length).toBeGreaterThan(0)
      expect(String(nav.mock.calls[0][0])).toContain('investigate')
    })
  })

  it('Escape closes the palette', () => {
    const close = vi.fn()
    render(<CommandPalette onClose={close} onNavigate={() => undefined} currentView="command" />)
    fireEvent.keyDown(screen.getByLabelText(/Command search/i), { key: 'Escape' })
    expect(close.mock.calls.length).toBe(1)
  })

  it('builds real context actions from the current route scope', () => {
    const params = new URLSearchParams({
      question_type: 'LAP_PERFORMANCE', driver_a: 'max-verstappen',
      driver_b: 'sergio-perez', season: '2023', round: '1', lap_number: '6',
    })
    render(
      <CommandPalette
        onClose={() => undefined} onNavigate={() => undefined}
        currentView="investigate" currentParams={params}
      />,
    )
    expect(screen.getByText('Run counterfactual with this scope')).toBeTruthy()
    expect(screen.getByText('Falsify this scope in the matrix')).toBeTruthy()
    expect(screen.getByText('Open graph for this scope')).toBeTruthy()
    expect(screen.getByText('Replay this scope')).toBeTruthy()
    expect(screen.getByText('Change context')).toBeTruthy()
  })

  it('context actions navigate with the real scope params', () => {
    const nav = vi.fn()
    const params = new URLSearchParams({
      driver_a: 'max-verstappen', driver_b: 'sergio-perez',
      season: '2023', round: '1', lap_number: '6',
    })
    render(
      <CommandPalette
        onClose={() => undefined} onNavigate={nav}
        currentView="investigate" currentParams={params}
      />,
    )
    fireEvent.click(screen.getByText('Run counterfactual with this scope'))
    const target = String(nav.mock.calls[0][0])
    expect(target).toContain('counterfactual?')
    expect(target).toContain('driver=sergio-perez')
    expect(target).toContain('reference=max-verstappen')
    expect(target).toContain('lap=6')
  })

  it('renders no context section without a scope', () => {
    render(<CommandPalette onClose={() => undefined} onNavigate={() => undefined} currentView="command" />)
    expect(screen.queryByText('This scope')).toBeNull()
  })
})
