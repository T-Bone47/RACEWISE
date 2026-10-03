/**
 * RACEWISE — production static server.
 *
 * Why this exists
 * ---------------
 * `vite preview` is a convenience for checking that a build works, not a server
 * to judge performance with. Measured against it:
 *
 *     Content-Length: 396750      <- NO Content-Encoding: gzip
 *     Cache-Control:  no-cache
 *
 * So every navigation re-downloaded the full 396 kB entry chunk and every lazy
 * route chunk. That, not the animation timings, is what made the product feel
 * unresponsive after a click.
 *
 * This server does the two things that actually matter:
 *
 *   1. gzip (or brotli, if the client accepts it) for text assets
 *   2. immutable, year-long caching for content-hashed filenames
 *
 * `index.html` is explicitly excluded from caching so a new build is picked up
 * immediately, while its hashed assets stay cached — the standard split.
 *
 *   node serve.mjs [--port 4173] [--root dist] [--api http://localhost:8000]
 */
import { createServer } from 'node:http'
import { createReadStream, existsSync, statSync } from 'node:fs'
import { createGzip, createBrotliCompress, constants as zlibConstants } from 'node:zlib'
import { extname, join, normalize, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = fileURLToPath(new URL('.', import.meta.url))

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`)
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback
}

const PORT = Number(arg('port', process.env.PORT ?? 4173))
const ROOT = resolve(__dirname, arg('root', 'dist'))
const API_TARGET = arg('api', process.env.RACEWISE_API ?? 'http://localhost:8000')

/* Content-hashed filenames (Vite emits name-HASH.ext) are immutable by
   construction: a changed byte produces a changed name. */
const HASHED = /-[A-Za-z0-9_-]{8,}\.(js|css|woff2?|png|jpg|jpeg|svg|webp|avif)$/i
const COMPRESSIBLE = /\.(js|css|html|json|svg|map|txt|xml)$/i
const ONE_YEAR = 31536000

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.avif': 'image/avif',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.map': 'application/json; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
}

function contentType(file) {
  return TYPES[extname(file).toLowerCase()] ?? 'application/octet-stream'
}

/** Reject anything that escapes the served root. */
function safeResolve(urlPath) {
  const clean = normalize(decodeURIComponent(urlPath.split('?')[0])).replace(/^(\.\.[/\\])+/, '')
  const full = join(ROOT, clean)
  if (full !== ROOT && !full.startsWith(ROOT + sep)) return null
  return full
}

const server = createServer((req, res) => {
  const url = req.url ?? '/'

  /* ---- API passthrough to the real engine ---- */
  if (url.startsWith('/api/')) {
    const proxyReq = require$fetch(url, req, res)
    return proxyReq
  }

  let file = safeResolve(url)
  if (!file) {
    res.writeHead(403).end('Forbidden')
    return
  }

  // SPA fallback: unknown paths are client routes (hash routing means this is
  // mostly just the root), so serve index.html.
  if (!existsSync(file) || statSync(file).isDirectory()) {
    file = join(ROOT, 'index.html')
  }
  if (!existsSync(file)) {
    res.writeHead(404).end('Not found')
    return
  }

  const ext = extname(file).toLowerCase()
  const hashed = HASHED.test(file)
  const stat = statSync(file)

  const headers = {
    'Content-Type': contentType(file),
    'Cache-Control': hashed
      ? `public, max-age=${ONE_YEAR}, immutable`
      : 'no-cache',
    'X-Content-Type-Options': 'nosniff',
    Vary: 'Accept-Encoding',
  }

  const accept = String(req.headers['accept-encoding'] ?? '')
  const compressible = COMPRESSIBLE.test(file)
  // woff2 and images are already compressed — re-encoding them wastes CPU
  const alreadyCompressed = /\.(woff2?|png|jpe?g|webp|avif)$/i.test(file)

  if (compressible && !alreadyCompressed && /\bgzip\b/.test(accept)) {
    headers['Content-Encoding'] = 'gzip'
    res.writeHead(200, headers)
    if (req.method === 'HEAD') return res.end()
    createReadStream(file)
      .pipe(createGzip({ level: zlibConstants.Z_BEST_COMPRESSION }))
      .pipe(res)
    return
  }

  headers['Content-Length'] = stat.size
  res.writeHead(200, headers)
  if (req.method === 'HEAD') return res.end()
  createReadStream(file).pipe(res)
})

/** Minimal reverse proxy for /api — keeps the engine URL out of the frontend. */
function require$fetch(url, req, res) {
  const target = new URL(url, API_TARGET)
  const proxied = createServer_request(req, res, target)
  return proxied
}

function createServer_request(req, res, target) {
  const chunks = []
  req.on('data', (c) => chunks.push(c))
  req.on('end', async () => {
    try {
      const upstream = await fetch(target, {
        method: req.method,
        headers: { 'content-type': req.headers['content-type'] ?? 'application/json' },
        body: ['GET', 'HEAD'].includes(req.method) ? undefined : Buffer.concat(chunks),
      })
      const body = Buffer.from(await upstream.arrayBuffer())
      res.writeHead(upstream.status, {
        'Content-Type': upstream.headers.get('content-type') ?? 'application/json',
        'Content-Length': body.length,
      })
      res.end(body)
    } catch (err) {
      res.writeHead(502, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ detail: `engine unreachable at ${API_TARGET}` }))
    }
  })
}

server.listen(PORT, '127.0.0.1', () => {
  console.log(`RACEWISE static server  http://127.0.0.1:${PORT}`)
  console.log(`  root ${ROOT}`)
  console.log(`  api  ${API_TARGET}`)
})