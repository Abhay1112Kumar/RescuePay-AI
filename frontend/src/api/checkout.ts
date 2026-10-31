export type PaymentStatus = 'PENDING' | 'CREATION_UNCERTAIN' | 'CREATED' | 'APPROVED' | 'CAPTURING' | 'CAPTURE_PENDING' | 'CAPTURE_UNCERTAIN' | 'COMPLETED' | 'FAILED' | 'VOIDED'
export interface Money { currency_code: 'USD'; value: string }
export interface DemoItem { item_id: string; name: string; amount: Money }
export interface DemoCatalog {
  mode: 'sandbox'; demo: true; items: DemoItem[]
  checkout_available: boolean; blocking_reasons: string[]; return_origin: string | null
}
export interface CreatedOrder {
  order_id: string; payment_id: string; request_id: string; status: PaymentStatus
  approval_url?: string
}
export interface VerifiedPayment {
  order_id: string; payment_id: string; status: PaymentStatus; capture_id: string | null; amount: Money
}
export interface PaymentRecord extends VerifiedPayment {
  reference_id: string; paypal_status: string | null; provider_refreshed: boolean
  created_at: string; updated_at: string
}
export interface CheckoutApi {
  catalog(signal?: AbortSignal): Promise<DemoCatalog>
  create(itemId: string, key: string, signal?: AbortSignal): Promise<CreatedOrder>
  status(orderId: string, signal?: AbortSignal): Promise<PaymentRecord>
  capture(orderId: string, signal?: AbortSignal): Promise<VerifiedPayment>
}

export class CheckoutApiError extends Error {
  code: string
  httpStatus?: number
  constructor(code: string, httpStatus?: number) {
    super('Sandbox request could not be verified.')
    this.code = code
    this.httpStatus = httpStatus
  }
}

export const isOrderId = (value: unknown): value is string => typeof value === 'string' && /^[A-Za-z0-9]{10,32}$/.test(value)
export const isUuid = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(value)
export const isItemId = (value: unknown): value is string => typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(value)
const statuses = new Set<PaymentStatus>(['PENDING', 'CREATION_UNCERTAIN', 'CREATED', 'APPROVED', 'CAPTURING', 'CAPTURE_PENDING', 'CAPTURE_UNCERTAIN', 'COMPLETED', 'FAILED', 'VOIDED'])
const nonempty = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0 && value.length <= 256
function object(value: unknown): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) throw new CheckoutApiError('INVALID_RESPONSE')
  return value as Record<string, unknown>
}
function paymentStatus(value: unknown): PaymentStatus {
  if (typeof value !== 'string' || !statuses.has(value as PaymentStatus)) throw new CheckoutApiError('INVALID_RESPONSE')
  return value as PaymentStatus
}
export function parseMoney(value: unknown): Money {
  const money = object(value)
  if (money.currency_code !== 'USD' || typeof money.value !== 'string' || !/^(?:0|[1-9]\d{0,7})\.\d{2}$/.test(money.value) || Number(money.value) <= 0) throw new CheckoutApiError('INVALID_RESPONSE')
  return { currency_code: 'USD', value: money.value }
}

export function safeSandboxApproval(value: unknown, orderId: string): string | null {
  if (typeof value !== 'string') return null
  try {
    const url = new URL(value)
    if (url.protocol !== 'https:' || url.hostname !== 'www.sandbox.paypal.com' || (url.port && url.port !== '443') || url.username || url.password || url.pathname !== '/checkoutnow' || url.hash) return null
    const tokens = url.searchParams.getAll('token')
    return tokens.length === 1 && tokens[0] === orderId ? url.href : null
  } catch { return null }
}

export function parseCatalog(value: unknown): DemoCatalog {
  const body = object(value)
  if (body.mode !== 'sandbox' || body.demo !== true || typeof body.checkout_available !== 'boolean' || !Array.isArray(body.items) || body.items.length > 20 || !Array.isArray(body.blocking_reasons) || !body.blocking_reasons.every(nonempty)) throw new CheckoutApiError('INVALID_RESPONSE')
  if (body.return_origin !== null) {
    if (typeof body.return_origin !== 'string') throw new CheckoutApiError('INVALID_RESPONSE')
    try {
      const url = new URL(body.return_origin)
      if (!['http:', 'https:'].includes(url.protocol) || !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) || url.origin !== body.return_origin) throw new Error('origin')
    } catch { throw new CheckoutApiError('INVALID_RESPONSE') }
  }
  if (body.checkout_available && (body.blocking_reasons.length > 0 || body.return_origin === null)) throw new CheckoutApiError('INVALID_RESPONSE')
  const items = body.items.map((value) => {
    const item = object(value)
    if (!isItemId(item.item_id) || !nonempty(item.name)) throw new CheckoutApiError('INVALID_RESPONSE')
    return { item_id: item.item_id, name: item.name, amount: parseMoney(item.amount) }
  })
  if (new Set(items.map((item) => item.item_id)).size !== items.length) throw new CheckoutApiError('INVALID_RESPONSE')
  return { mode: 'sandbox', demo: true, items, checkout_available: body.checkout_available, blocking_reasons: body.blocking_reasons as string[], return_origin: body.return_origin as string | null }
}

export function parseCreatedOrder(value: unknown): CreatedOrder {
  const body = object(value)
  if (!isOrderId(body.order_id) || !isUuid(body.payment_id) || !isUuid(body.request_id) || !Array.isArray(body.links)) throw new CheckoutApiError('INVALID_RESPONSE')
  const status = paymentStatus(body.status)
  let approval: string | undefined
  for (const raw of body.links) {
    const link = object(raw)
    if (link.rel === 'approve' || link.rel === 'payer-action') {
      const safe = link.method === 'GET' ? safeSandboxApproval(link.href, body.order_id) : null
      if (!safe || (approval && approval !== safe)) throw new CheckoutApiError('INVALID_RESPONSE')
      approval = safe
    }
  }
  if (['CREATED', 'APPROVED'].includes(status) && !approval) throw new CheckoutApiError('INVALID_RESPONSE')
  return { order_id: body.order_id, payment_id: body.payment_id, request_id: body.request_id, status, approval_url: approval }
}

export function parsePayment(value: unknown): VerifiedPayment {
  const body = object(value)
  if (!isOrderId(body.order_id) || !isUuid(body.payment_id) || !(body.capture_id === null || nonempty(body.capture_id))) throw new CheckoutApiError('INVALID_RESPONSE')
  const status = paymentStatus(body.status)
  if (['COMPLETED', 'CAPTURE_PENDING'].includes(status) && !nonempty(body.capture_id)) throw new CheckoutApiError('INVALID_RESPONSE')
  return { order_id: body.order_id, payment_id: body.payment_id, capture_id: body.capture_id as string | null, status, amount: parseMoney(body.amount) }
}

export function parsePaymentRecord(value: unknown): PaymentRecord {
  const body = object(value)
  const payment = parsePayment(body)
  if (!isItemId(body.reference_id) || typeof body.provider_refreshed !== 'boolean' || !(body.paypal_status === null || nonempty(body.paypal_status)) || typeof body.created_at !== 'string' || !Number.isFinite(Date.parse(body.created_at)) || typeof body.updated_at !== 'string' || !Number.isFinite(Date.parse(body.updated_at))) throw new CheckoutApiError('INVALID_RESPONSE')
  return { ...payment, reference_id: body.reference_id, provider_refreshed: body.provider_refreshed, paypal_status: body.paypal_status as string | null, created_at: body.created_at, updated_at: body.updated_at }
}

export function createCheckoutApi(fetcher: typeof fetch = fetch, deadlines = { catalog: 8000, status: 45000, create: 120000, capture: 120000 }): CheckoutApi {
  async function request(path: string, method: string, timeoutMs: number, signal?: AbortSignal, body?: unknown, key?: string): Promise<unknown> {
    signal?.throwIfAborted()
    const controller = new AbortController()
    const cancel = () => controller.abort()
    signal?.addEventListener('abort', cancel, { once: true })
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    try {
      const response = await fetcher(path, {
        method, credentials: 'omit', cache: 'no-store', redirect: 'error', signal: controller.signal,
        headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(key ? { 'Idempotency-Key': key } : {}) },
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      })
      const json = /^application\/(?:[\w.+-]+\+)?json(?:\s*;|$)/i.test(response.headers.get('content-type') ?? '')
      if (!response.ok) {
        let code = 'HTTP_ERROR'
        if (json) {
          try {
            const payload = object(await response.json())
            if (typeof payload.error_code === 'string' && /^[A-Z_]{1,80}$/.test(payload.error_code)) code = payload.error_code
          } catch (error) { if (controller.signal.aborted) throw error }
        }
        throw new CheckoutApiError(code, response.status)
      }
      if (!json) throw new CheckoutApiError('INVALID_RESPONSE')
      try { return await response.json() } catch (error) {
        if (controller.signal.aborted) throw error
        throw new CheckoutApiError('INVALID_RESPONSE')
      }
    } catch (error) {
      signal?.throwIfAborted()
      if (error instanceof CheckoutApiError) throw error
      throw new CheckoutApiError(controller.signal.aborted ? 'TIMEOUT' : 'NETWORK')
    } finally {
      clearTimeout(timer)
      signal?.removeEventListener('abort', cancel)
    }
  }
  return {
    catalog: async (signal) => parseCatalog(await request('/api/v1/sandbox/catalog', 'GET', deadlines.catalog, signal)),
    create: async (itemId, key, signal) => parseCreatedOrder(await request('/api/v1/payments/orders', 'POST', deadlines.create, signal, { item_id: itemId }, key)),
    status: async (orderId, signal) => {
      if (!isOrderId(orderId)) throw new CheckoutApiError('INVALID_IDENTITY')
      return parsePaymentRecord(await request(`/api/v1/payments/orders/${orderId}`, 'GET', deadlines.status, signal))
    },
    capture: async (orderId, signal) => {
      if (!isOrderId(orderId)) throw new CheckoutApiError('INVALID_IDENTITY')
      return parsePayment(await request(`/api/v1/payments/orders/${orderId}/capture`, 'POST', deadlines.capture, signal))
    },
  }
}
