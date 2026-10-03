/* ============ build-identity guard tests ============
   The bug this prevents: a tab left open across a rebuild kept running the old
   bundle forever, because hash routing never re-executes JavaScript. The guard
   compares the stamp compiled into the running bundle against the stamp the
   server is advertising, and reloads only when they disagree.

   These tests assert the *policy*, not the reload — a test must never navigate. */
import { describe, expect, it } from 'vitest'
import { parseServerStamp, runningStamp, staleDecision } from './build-version'

describe('build identity', () => {
  describe('parseServerStamp', () => {
    it('reads the stamp vite injected into index.html', () => {
      expect(parseServerStamp('<meta name="x-rw-build" content="2026-10-03T09:00:00.000Z" />')).toBe(
        '2026-10-03T09:00:00.000Z',
      )
    })

    it('tolerates attribute order and quoting differences', () => {
      expect(parseServerStamp(`<meta content='abc' name='x-rw-build' />`)).toBe('abc')
    })

    it('returns null when the marker is absent — an unmarked index is not a failure', () => {
      expect(parseServerStamp('<html><head><title>RACEWISE</title></head></html>')).toBeNull()
    })
  })

  it('reports no running stamp outside a built bundle rather than throwing', () => {
    /* Unit tests do not apply vite `define`, so this is the real no-stamp path. */
    expect(runningStamp()).toBeNull()
  })

  describe('staleDecision', () => {
    it('reloads when the server is on a different build', () => {
      expect(
        staleDecision({ running: 'build-a', server: 'build-b', alreadyReloadedFor: null }),
      ).toBe('reload')
    })

    it('holds when the tab is already on the served build', () => {
      expect(
        staleDecision({ running: 'build-b', server: 'build-b', alreadyReloadedFor: null }),
      ).toBe('hold')
    })

    it('holds instead of looping when a reload already happened for that build', () => {
      /* Without this, a reload that fails to pick up the new bundle would
         re-fire on every focus event and the tab would be unusable. */
      expect(
        staleDecision({ running: 'build-a', server: 'build-b', alreadyReloadedFor: 'build-b' }),
      ).toBe('hold')
    })

    it('allows a second reload once a newer build is served', () => {
      expect(
        staleDecision({ running: 'build-a', server: 'build-c', alreadyReloadedFor: 'build-b' }),
      ).toBe('reload')
    })

    it('holds when the server stamp cannot be read', () => {
      /* A failed probe must never take the workstation down. */
      expect(
        staleDecision({ running: 'build-a', server: null, alreadyReloadedFor: null }),
      ).toBe('hold')
    })

    it('holds when the running stamp is unknown', () => {
      expect(
        staleDecision({ running: null, server: 'build-b', alreadyReloadedFor: null }),
      ).toBe('hold')
    })
  })

  describe('vite wiring', () => {
    it('stamps the same value into index.html and the bundle define', async () => {
      /* The guard is only as good as this: if the two stamps came from different
         places, or the placeholder were dropped, the check would silently never
         fire. Read the real config rather than trusting the comment. */
      const { readFileSync } = await import('node:fs')
      const { resolve } = await import('node:path')
      const root = process.cwd()
      const cfg = readFileSync(resolve(root, 'vite.config.ts'), 'utf8')
      const html = readFileSync(resolve(root, 'index.html'), 'utf8')

      expect(cfg).toContain('name="x-rw-build"')
      expect(cfg).toContain('__RW_BUILD__')
      /* One constant feeds both; the config must not build the stamp twice. */
      expect(cfg.match(/new Date\(\)\.toISOString\(\)/g) ?? []).toHaveLength(1)
      expect(html).toContain('<!--RW_BUILD_STAMP-->')
    })
  })
})