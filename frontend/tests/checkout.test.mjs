import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  CheckoutApiError, createCheckoutApi, parseCatalog, parseCreatedOrder, parsePaymentRecord,
  safeSandboxApproval,
} from '../src/api/checkout.ts'
import { CHECKOUT_STORAGE_KEY, CheckoutController } from '../src/checkout/controller.ts'

// Every payment below is a synthetic test fixture. No PayPal URL is fetched/opened.
const orderId = '5O190127TN364715T'
const paymentId = '0d0c7a2e-3f52-4b6f-9d8e-3a1c6c0f5e21'
const key = '11111111-1111-4111-8111-111111111111'
const itemId = 'demo-notebook-v1'
const amount = { currency_code: 'USD', value: '1.00' }
const approval = `https://www.sandbox.paypal.com/checkoutnow?token=${orderId}`
const catalog = () => ({ mode: 'sandbox', demo: true, checkout_available: true, blocking_reasons: [], return_origin: 'http://127.0.0.1:5174', items: [
  { item_id: itemId, name: 'Synthetic catalog response: notebook', amount: { ...amount } },
  { item_id: 'demo-stickers-v1', name: 'Synthetic catalog response: stickers', amount: { currency_code: 'USD', value: '2.50' } },
] })
const created = () => ({ order_id: orderId, payment_id: paymentId, request_id: key, status: 'CREATED', approval_url: approval })
const creationBody = () => ({ ...created(), links: [{ rel: 'approve', method: 'GET', href: approval }] })
const captured = (status = 'COMPLETED') => ({ order_id: orderId, payment_id: paymentId, status, capture_id: ['COMPLETED', 'CAPTURE_PENDING'].includes(status) ? '1JS80234KJ293810L' : null, amount: { ...amount } })
const record = (status = 'CREATED') => ({ ...captured(status), reference_id: itemId, paypal_status: status, provider_refreshed: true, created_at: '2026-10-31T00:00:00Z', updated_at: '2026-10-31T00:01:00Z' })

class Session {
  values = new Map()
  getItem(key) { return this.values.get(key) ?? null }
  setItem(key, value) { this.values.set(key, value) }
  removeItem(key) { this.values.delete(key) }
}
function harness(overrides = {}, storage = new Session()) {
  const calls = { create: [], capture: [], status: [], redirects: [] }
  let sequence = 0
  const location = { origin: 'http://127.0.0.1:5174', pathname: '/checkout', search: '' }
  const api = {
    catalog: async () => catalog(),
    create: async (item, operationKey) => { calls.create.push([item, operationKey]); return created() },
    status: async (id) => { calls.status.push(id); return record() },
    capture: async (id) => { calls.capture.push(id); return captured() },
    ...overrides,
  }
  const deps = {
    api, storage, location: () => location,
    redirect: (url) => { calls.redirects.push(url) },
    clearCallback: () => { location.pathname = '/checkout'; location.search = '' },
    uuid: () => { sequence += 1; return `${String(sequence).padStart(8, '0')}-1111-4111-8111-111111111111` },
  }
  return { api, calls, storage, location, controller: new CheckoutController(deps), fresh: () => new CheckoutController(deps) }
}

test('approval links require the intended HTTPS Sandbox host, path and exact bound token', () => {
  assert.equal(safeSandboxApproval(approval, orderId), approval)
  for (const url of [
    approval.replace('www.sandbox.paypal.com', 'www.paypal.com'),
    approval.replace('www.sandbox.paypal.com', 'www.sandbox.paypal.com.evil.test'),
    approval.replace('https:', 'http:'), approval.replace('/checkoutnow', '/other'),
    `${approval}&token=${orderId}`, `${approval}#untrusted`,
    approval.replace(orderId, 'OTHERORDER12345'),
    approval.replace('https://', 'https://user:pass@'), 'javascript:alert(1)',
  ]) assert.equal(safeSandboxApproval(url, orderId), null, url)
})

test('runtime parsers reject fabricated readiness, malformed identities and missing capture evidence', () => {
  assert.equal(parseCatalog(catalog()).items[0].amount.value, '1.00')
  for (const invalid of [null, { ...catalog(), mode: 'live' }, { ...catalog(), demo: false }, { ...catalog(), blocking_reasons: ['DATABASE_NOT_READY'] }, { ...catalog(), items: [catalog().items[0], catalog().items[0]] }]) assert.throws(() => parseCatalog(invalid))
  assert.equal(parseCreatedOrder(creationBody()).approval_url, approval)
  assert.throws(() => parseCreatedOrder({ ...creationBody(), links: [{ rel: 'approve', method: 'GET', href: approval.replace('sandbox.', '') }] }))
  assert.throws(() => parsePaymentRecord({ ...record('COMPLETED'), capture_id: null }))
  assert.throws(() => parsePaymentRecord({ ...record(), provider_refreshed: 'yes' }))
  assert.throws(() => parsePaymentRecord({ ...record(), amount: { value: '1.00', currency_code: 'EUR' } }))
})

test('HTTP adapter submits item ID and stable key only, with no credentials or redirects', async () => {
  const sent = []
  const api = createCheckoutApi(async (url, options) => { sent.push([url, options]); return Response.json(creationBody(), { status: 201 }) })
  await api.create(itemId, key)
  await api.create(itemId, key)
  for (const [url, options] of sent) {
    assert.equal(url, '/api/v1/payments/orders')
    assert.deepEqual(JSON.parse(options.body), { item_id: itemId })
    assert.equal(options.headers['Idempotency-Key'], key)
    assert.equal(options.credentials, 'omit')
    assert.equal(options.redirect, 'error')
  }
})

test('HTTP adapter rejects HTML/invalid JSON and sanitizes provider errors', async () => {
  for (const response of [new Response('<html>SPA</html>', { headers: { 'content-type': 'text/html' } }), new Response('bad', { headers: { 'content-type': 'application/json' } })]) {
    const api = createCheckoutApi(async () => response)
    await assert.rejects(api.capture(orderId), { code: 'INVALID_RESPONSE' })
  }
  const api = createCheckoutApi(async () => Response.json({ detail: 'private diagnostic', error_code: 'CAPTURE_OUTCOME_UNCERTAIN' }, { status: 409 }))
  await assert.rejects(api.capture(orderId), (error) => error.code === 'CAPTURE_OUTCOME_UNCERTAIN' && !error.message.includes('private diagnostic'))
})

test('payment deadline covers slow body reading and caller cancellation is preserved', async () => {
  const api = createCheckoutApi(async (_url, { signal }) => new Response(new ReadableStream({ start(controller) {
    signal.addEventListener('abort', () => controller.error(new DOMException('Abort', 'AbortError')), { once: true })
  } }), { headers: { 'content-type': 'application/json' } }), { catalog: 10, create: 10, status: 10, capture: 10 })
  await assert.rejects(api.capture(orderId), { code: 'TIMEOUT' })
  const caller = new AbortController()
  caller.abort()
  await assert.rejects(api.status(orderId, caller.signal), { name: 'AbortError' })
})

test('mocked full flow binds identity across approval/return and verifies capture', async () => {
  const h = harness()
  await h.controller.start()
  await h.controller.create()
  const saved = JSON.parse(h.storage.getItem(CHECKOUT_STORAGE_KEY))
  assert.equal(saved.orderId, orderId)
  assert.equal(h.controller.getSnapshot().phase, 'awaiting-approval')
  h.controller.approve()
  assert.deepEqual(h.calls.redirects, [approval])
  h.controller.stop()
  h.location.pathname = '/payment/return'
  h.location.search = `?token=${orderId}&PayerID=not-stored`
  h.api.status = async () => record('APPROVED')
  const returned = h.fresh()
  await returned.start()
  assert.equal(returned.getSnapshot().phase, 'completed')
  assert.deepEqual(h.calls.capture, [orderId])
  assert.equal(JSON.parse(h.storage.getItem(CHECKOUT_STORAGE_KEY)).captureAttempted, true)
  assert.equal(h.storage.getItem(CHECKOUT_STORAGE_KEY).includes('not-stored'), false)
  assert.equal(h.location.pathname, '/checkout')
  returned.stop()
})

test('lost creation response and reload retain the exact operation key', async () => {
  const h = harness()
  h.api.create = async (item, operationKey) => { h.calls.create.push([item, operationKey]); throw new CheckoutApiError('TIMEOUT') }
  await h.controller.start()
  await h.controller.create()
  assert.equal(h.controller.getSnapshot().phase, 'uncertain')
  const originalKey = h.calls.create[0][1]
  assert.equal(h.controller.canStartNew(), false)
  h.controller.newCheckout()
  h.controller.stop()
  h.api.create = async (item, operationKey) => { h.calls.create.push([item, operationKey]); return created() }
  const restored = h.fresh()
  await restored.start()
  await restored.create()
  assert.deepEqual(h.calls.create.map((call) => call[1]), [originalKey, originalKey])
  restored.stop()
})

test('duplicate create clicks share one in-flight request and item selection locks', async () => {
  let release
  const h = harness()
  h.api.create = async (item, operationKey) => { h.calls.create.push([item, operationKey]); return new Promise((resolve) => { release = resolve }) }
  await h.controller.start()
  const pending = h.controller.create()
  await h.controller.create()
  h.controller.choose('demo-stickers-v1')
  assert.equal(h.calls.create.length, 1)
  assert.equal(h.controller.getSnapshot().selectedItemId, itemId)
  release(created())
  await pending
  h.controller.stop()
})

for (const suffix of ['?token=OTHERORDER12345', `?token=${orderId}&token=${orderId}`, '']) test(`mismatched/missing return token causes no lookup or capture (${suffix})`, async () => {
  const h = harness()
  await h.controller.start(); await h.controller.create(); h.controller.stop()
  h.location.pathname = '/payment/return'; h.location.search = suffix
  const returned = h.fresh(); await returned.start()
  assert.equal(returned.getSnapshot().phase, 'error')
  assert.equal(h.calls.status.length, 0); assert.equal(h.calls.capture.length, 0)
  returned.stop()
})

test('an unbound return token without a local operation never initiates capture', async () => {
  const h = harness()
  h.location.pathname = '/payment/return'; h.location.search = `?token=${orderId}`
  await h.controller.start()
  assert.equal(h.controller.getSnapshot().phase, 'error')
  assert.equal(h.calls.create.length + h.calls.status.length + h.calls.capture.length, 0)
  h.controller.stop()
})

test('cancel is local intent, not payment failure/void proof; same order can resume approval', async () => {
  const h = harness()
  await h.controller.start(); await h.controller.create(); h.controller.stop()
  h.location.pathname = '/payment/cancel'; h.location.search = `?token=${orderId}`
  const cancelled = h.fresh(); await cancelled.start()
  assert.equal(cancelled.getSnapshot().phase, 'cancelled')
  assert.equal(h.calls.capture.length, 0)
  assert.equal(cancelled.getSnapshot().payment.status, 'CREATED')
  const sameKey = cancelled.getSnapshot().operation.key
  cancelled.approve()
  assert.deepEqual(h.calls.redirects, [approval])
  assert.equal(cancelled.getSnapshot().operation.key, sameKey)
  cancelled.stop()
})

test('capture timeout survives reload/duplicate return; only status reconciliation follows', async () => {
  const h = harness()
  await h.controller.start(); await h.controller.create(); h.controller.stop()
  h.api.status = async () => record('APPROVED')
  h.api.capture = async (id) => { h.calls.capture.push(id); throw new CheckoutApiError('TIMEOUT') }
  h.location.pathname = '/payment/return'; h.location.search = `?token=${orderId}`
  const returned = h.fresh(); await returned.start()
  assert.equal(returned.getSnapshot().phase, 'uncertain')
  assert.equal(returned.canStartNew(), false)
  returned.stop()
  h.location.pathname = '/payment/return'; h.location.search = `?token=${orderId}`
  const reloaded = h.fresh(); await reloaded.start(); await reloaded.captureApproved(); await reloaded.refresh()
  assert.equal(reloaded.getSnapshot().phase, 'uncertain')
  assert.equal(h.calls.capture.length, 1)
  h.api.status = async () => record('COMPLETED')
  await reloaded.refresh()
  assert.equal(reloaded.getSnapshot().phase, 'completed')
  reloaded.stop()
})

for (const status of ['CAPTURING', 'CAPTURE_PENDING', 'CAPTURE_UNCERTAIN', 'APPROVED', 'FAILED', 'VOIDED']) test(`HTTP 200 ${status} is never displayed as paid`, async () => {
  const h = harness()
  await h.controller.start(); await h.controller.create()
  h.api.status = async () => record(status)
  await h.controller.refresh()
  assert.notEqual(h.controller.getSnapshot().phase, 'completed')
  assert.equal(h.calls.capture.length, 0)
  h.controller.stop()
})

test('stale approval cannot trigger auto capture, even with a matching return', async () => {
  const h = harness()
  await h.controller.start(); await h.controller.create(); h.controller.stop()
  h.api.status = async () => ({ ...record('APPROVED'), provider_refreshed: false })
  h.location.pathname = '/payment/return'; h.location.search = `?token=${orderId}`
  const returned = h.fresh(); await returned.start()
  assert.equal(returned.canCapture(), false)
  assert.equal(h.calls.capture.length, 0)
  returned.stop()
})

for (const patch of [{ order_id: 'OTHERORDER12345' }, { payment_id: key }, { reference_id: 'other-item' }, { amount: { currency_code: 'USD', value: '0.01' } }]) test(`wrong backend identity/money cannot display success: ${Object.keys(patch)[0]}`, async () => {
  const h = harness()
  await h.controller.start(); await h.controller.create()
  h.api.status = async () => ({ ...record('COMPLETED'), ...patch })
  await h.controller.refresh()
  assert.equal(h.controller.getSnapshot().phase, 'uncertain')
  assert.equal(h.controller.getSnapshot().payment, null)
  h.controller.stop()
})

test('health-equivalent configuration alone cannot enable checkout with missing setup/origin mismatch', async () => {
  for (const response of [{ ...catalog(), checkout_available: false, blocking_reasons: ['PAYPAL_NOT_CONFIGURED'] }, { ...catalog(), return_origin: 'http://localhost:5173' }]) {
    const h = harness({ catalog: async () => response })
    await h.controller.start(); await h.controller.create()
    assert.equal(h.controller.configured(), false)
    assert.equal(h.calls.create.length, 0)
    h.controller.stop()
  }
})

test('storage failure prevents creation/capture; corrupted identity is not silently discarded', async () => {
  const storage = new Session()
  storage.setItem(CHECKOUT_STORAGE_KEY, 'corrupt')
  const h = harness({}, storage)
  await h.controller.start(); await h.controller.create()
  assert.equal(h.controller.getSnapshot().storageProblem, true)
  assert.equal(h.calls.create.length, 0)
  assert.equal(storage.getItem(CHECKOUT_STORAGE_KEY), 'corrupt')
  h.controller.stop()
  const blocked = harness({}, { getItem: () => null, setItem: () => { throw new Error('denied') }, removeItem: () => {} })
  await blocked.controller.start(); await blocked.controller.create()
  assert.equal(blocked.calls.create.length, 0)
  blocked.controller.stop()
})

test('capture-attempt flag must persist before a capture POST is sent', async () => {
  const h = harness()
  await h.controller.start(); await h.controller.create()
  h.api.status = async () => record('APPROVED')
  await h.controller.refresh()
  h.storage.setItem = () => { throw new Error('storage full') }
  await h.controller.captureApproved()
  assert.equal(h.calls.capture.length, 0)
  assert.equal(h.controller.getSnapshot().storageProblem, true)
  h.controller.stop()
})

test('a new operation key is generated only after an explicit new checkout', async () => {
  const h = harness()
  await h.controller.start(); await h.controller.create()
  const firstKey = h.controller.getSnapshot().operation.key
  h.api.status = async () => record('COMPLETED')
  await h.controller.refresh()
  h.controller.newCheckout()
  h.controller.choose('demo-stickers-v1')
  await h.controller.create()
  assert.notEqual(h.calls.create[1][1], firstKey)
  assert.equal(h.calls.create[1][0], 'demo-stickers-v1')
  h.controller.stop()
})

test('capture errors cannot authorize a replacement checkout without verified terminal status', async () => {
  for (const code of ['ORDER_NOT_APPROVED', 'PAYMENT_INSTRUMENT_DECLINED', 'PAYMENT_INVALID_STATE', 'AMOUNT_MISMATCH', 'PAYMENT_VERIFICATION_FAILED', 'TIMEOUT']) {
    const h = harness()
    await h.controller.start(); await h.controller.create()
    h.api.status = async () => record('APPROVED')
    await h.controller.refresh()
    h.api.capture = async () => { throw new CheckoutApiError(code, 409) }
    await h.controller.captureApproved()
    const savedKey = h.controller.getSnapshot().operation.key
    assert.equal(h.controller.canStartNew(), false)
    h.controller.newCheckout()
    assert.equal(h.controller.getSnapshot().operation.key, savedKey)
    assert.equal(h.controller.canCapture(), false)
    h.api.status = async () => record('FAILED')
    await h.controller.refresh()
    assert.equal(h.controller.canStartNew(), true)
    h.controller.stop()
  }
})

test('strict-mode style cleanup cancels stale work without publishing a second capture', async () => {
  const h = harness()
  await h.controller.start(); await h.controller.create(); h.controller.stop()
  h.api.status = async () => record('APPROVED')
  let finishCapture
  h.api.capture = async (id) => { h.calls.capture.push(id); return new Promise((resolve) => { finishCapture = resolve }) }
  h.location.pathname = '/payment/return'; h.location.search = `?token=${orderId}`
  const returned = h.fresh()
  const firstStart = returned.start()
  while (!finishCapture) await new Promise((resolve) => setTimeout(resolve, 0))
  returned.stop()
  await returned.start()
  finishCapture(captured())
  await firstStart
  assert.equal(h.calls.capture.length, 1)
  assert.equal(returned.getSnapshot().phase, 'uncertain')
  returned.stop()
})
