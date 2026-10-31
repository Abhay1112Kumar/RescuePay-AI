export interface BackendHealth {
  status: 'ok'
  service: string
  version: string
}

export type HealthUnavailableReason = 'network' | 'timeout' | 'http' | 'invalid-response'

export type HealthCheckResult =
  | { status: 'connected'; data: BackendHealth }
  | { status: 'unavailable'; reason: HealthUnavailableReason; httpStatus?: number }

export type BackendHealthState = { status: 'checking' } | HealthCheckResult

interface HealthCheckOptions {
  signal?: AbortSignal
  timeoutMs?: number
  fetcher?: typeof fetch
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

// Follow the inspected backend implementation, not the older contract example.
// APP_NAME is configurable, so service must not be pinned to one literal name.
function parseHealth(value: unknown): BackendHealth | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return null

  const record = value as Record<string, unknown>
  if (record.status !== 'ok' || !isNonEmptyString(record.service) || !isNonEmptyString(record.version)) {
    return null
  }

  return { status: 'ok', service: record.service, version: record.version }
}

export async function checkBackendHealth({
  signal,
  timeoutMs = 5000,
  fetcher = fetch,
}: HealthCheckOptions = {}): Promise<HealthCheckResult> {
  signal?.throwIfAborted()
  const controller = new AbortController()
  const cancel = () => controller.abort()
  signal?.addEventListener('abort', cancel, { once: true })

  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)

  try {
    const response = await fetcher('/api/v1/health', {
      method: 'GET',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      credentials: 'omit',
      redirect: 'error',
      signal: controller.signal,
    })

    if (!response.ok) {
      return { status: 'unavailable', reason: 'http', httpStatus: response.status }
    }

    // An SPA fallback can return 200 HTML when /api routing is missing.
    const contentType = response.headers.get('content-type') ?? ''
    if (!/^application\/(?:[\w.+-]+\+)?json(?:\s*;|$)/i.test(contentType)) {
      return { status: 'unavailable', reason: 'invalid-response' }
    }

    let payload: unknown
    try {
      payload = await response.json()
    } catch (error) {
      if (controller.signal.aborted) throw error
      return { status: 'unavailable', reason: 'invalid-response' }
    }

    const data = parseHealth(payload)
    return data
      ? { status: 'connected', data }
      : { status: 'unavailable', reason: 'invalid-response' }
  } catch {
    // Component cleanup/caller cancellation must not publish a failed check.
    signal?.throwIfAborted()
    return { status: 'unavailable', reason: timedOut ? 'timeout' : 'network' }
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', cancel)
  }
}
