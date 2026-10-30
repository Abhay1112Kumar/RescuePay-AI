import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createServer as createHttpServer } from 'node:http'
import { once } from 'node:events'
import { fileURLToPath } from 'node:url'
import { createServer as createViteServer } from 'vite'
import { checkBackendHealth } from '../src/api/health.ts'

const healthy = { status: 'ok', service: 'RescuePay-AI', version: '0.1.0' }
const jsonResponse = (body) => Response.json(body)
const checkResponse = (response) => checkBackendHealth({ fetcher: async () => response })

test('validates the implemented health response and requests the same-origin endpoint', async () => {
  const result = await checkBackendHealth({
    fetcher: async (url, options) => {
      assert.equal(url, '/api/v1/health')
      assert.equal(options.method, 'GET')
      assert.equal(options.headers.Accept, 'application/json')
      assert.equal(options.cache, 'no-store')
      assert.equal(options.credentials, 'omit')
      assert.equal(options.redirect, 'error')
      assert.equal(options.signal.aborted, false)
      return jsonResponse(healthy)
    },
  })
  assert.deepEqual(result, { status: 'connected', data: healthy })
})

test('allows configured service names and drops unknown response fields', async () => {
  assert.deepEqual(await checkResponse(jsonResponse({ ...healthy, service: 'Custom workspace', extra: 'ignored' })), {
    status: 'connected',
    data: { ...healthy, service: 'Custom workspace' },
  })
})

test('rejects incomplete, unhealthy, or incorrectly typed JSON', async () => {
  for (const body of [
    null, [], 'ok', 42, {},
    { status: 'ok', service: 'rescuepay-backend' }, // Older contract example lacks version.
    { ...healthy, status: 'degraded' },
    { ...healthy, service: '' },
    { ...healthy, service: '   ' },
    { ...healthy, service: 123 },
    { ...healthy, version: null },
    { ...healthy, version: ' ' },
  ]) {
    assert.deepEqual(await checkResponse(jsonResponse(body)), { status: 'unavailable', reason: 'invalid-response' })
  }
})

test('rejects HTML SPA fallbacks even with HTTP 200', async () => {
  const response = new Response('<html>Dashboard</html>', { headers: { 'content-type': 'text/html' } })
  assert.deepEqual(await checkResponse(response), { status: 'unavailable', reason: 'invalid-response' })
})

test('rejects malformed JSON without exposing its body', async () => {
  const response = new Response('not-json', { headers: { 'content-type': 'application/json' } })
  assert.deepEqual(await checkResponse(response), { status: 'unavailable', reason: 'invalid-response' })
})

test('accepts JSON content types with a charset', async () => {
  const response = new Response(JSON.stringify(healthy), { headers: { 'content-type': 'application/json; charset=utf-8' } })
  assert.equal((await checkResponse(response)).status, 'connected')
})

test('reports unsuccessful HTTP responses without reading provider errors', async () => {
  for (const status of [404, 500, 503]) {
    const response = new Response('Private diagnostic body', { status })
    assert.deepEqual(await checkResponse(response), { status: 'unavailable', reason: 'http', httpStatus: status })
    assert.equal(response.bodyUsed, false)
  }
})

test('sanitizes network failures', async () => {
  const result = await checkBackendHealth({ fetcher: async () => { throw new TypeError('Private network detail') } })
  assert.deepEqual(result, { status: 'unavailable', reason: 'network' })
})

function waitForAbort(signal) {
  return new Promise((_, reject) => {
    signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
  })
}

test('aborts a slow request and reports timeout', async () => {
  let requestSignal
  const result = await checkBackendHealth({
    timeoutMs: 15,
    fetcher: async (_url, { signal }) => {
      requestSignal = signal
      return waitForAbort(signal)
    },
  })
  assert.equal(requestSignal.aborted, true)
  assert.deepEqual(result, { status: 'unavailable', reason: 'timeout' })
})

test('keeps the timeout active while reading a slow JSON body', async () => {
  const result = await checkBackendHealth({
    timeoutMs: 15,
    fetcher: async (_url, { signal }) => {
      const body = new ReadableStream({
        start(controller) {
          signal.addEventListener('abort', () => controller.error(new DOMException('Aborted', 'AbortError')), { once: true })
        },
      })
      return new Response(body, { headers: { 'content-type': 'application/json' } })
    },
  })
  assert.deepEqual(result, { status: 'unavailable', reason: 'timeout' })
})

test('propagates caller cancellation instead of publishing unavailable', async () => {
  const caller = new AbortController()
  const request = checkBackendHealth({
    signal: caller.signal,
    fetcher: async (_url, { signal }) => waitForAbort(signal),
  })
  caller.abort()
  await assert.rejects(request, { name: 'AbortError' })
})

test('does not send a request when already cancelled', async () => {
  const caller = new AbortController()
  caller.abort()
  await assert.rejects(checkBackendHealth({
    signal: caller.signal,
    fetcher: async () => assert.fail('Cancelled request must not be sent'),
  }), { name: 'AbortError' })
})

test('cleans up the request timer after a successful response', async () => {
  let requestSignal
  await checkBackendHealth({
    timeoutMs: 15,
    fetcher: async (_url, { signal }) => {
      requestSignal = signal
      return jsonResponse(healthy)
    },
  })
  await new Promise((resolve) => setTimeout(resolve, 30))
  assert.equal(requestSignal.aborted, false)
})

test('configured Vite proxy preserves /api routing using an isolated test fixture', async () => {
  const fixture = { status: 'ok', service: 'Health proxy test fixture', version: '0.1.0' }
  let validResponse = true
  const upstream = createHttpServer((request, response) => {
    assert.equal(request.url, '/api/v1/health')
    assert.equal(request.method, 'GET')
    response.writeHead(200, { 'Content-Type': 'application/json' })
    response.end(JSON.stringify(validResponse ? fixture : { status: 'ok' }))
  })
  upstream.listen(0, '127.0.0.1')
  await once(upstream, 'listening')

  const previousTarget = process.env.RESCUEPAY_API_TARGET
  process.env.RESCUEPAY_API_TARGET = `http://127.0.0.1:${upstream.address().port}`
  let vite
  try {
    vite = await createViteServer({
      configFile: fileURLToPath(new URL('../vite.config.ts', import.meta.url)),
      envFile: false,
      logLevel: 'silent',
      server: { host: '127.0.0.1', port: 0, strictPort: false, open: false },
    })
    await vite.listen()
    const origin = `http://127.0.0.1:${vite.httpServer.address().port}`
    const fetcher = (path, options) => fetch(new URL(path, origin), options)

    assert.deepEqual(await checkBackendHealth({ fetcher }), { status: 'connected', data: fixture })
    validResponse = false
    assert.deepEqual(await checkBackendHealth({ fetcher }), { status: 'unavailable', reason: 'invalid-response' })
  } finally {
    if (previousTarget === undefined) delete process.env.RESCUEPAY_API_TARGET
    else process.env.RESCUEPAY_API_TARGET = previousTarget
    await vite?.close()
    await new Promise((resolve, reject) => upstream.close((error) => error ? reject(error) : resolve()))
  }
})
