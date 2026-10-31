import { isOrderId, parseMoney, type Money, type PaymentStatus } from './checkout.ts'
export const actionLabels: Record<string, string> = {
  CHECK_STATUS: 'Check payment status separately (this may refresh provider evidence).',
  WAIT: 'Wait for settlement; do not repeat capture.',
  MANUAL_RECONCILIATION: 'Reconcile manually before another payment action.',
  REVIEW_RECORD: 'Review the stored record; later refunds/disputes are not covered.',
}
export interface PaymentEvidence {
  state: PaymentStatus; amount: Money; observed_at: string; record_updated_at: string
  uncertain: boolean; events_truncated: boolean
  facts: { code: string; text: string }[]
  events: { code: string; state: PaymentStatus | null; recorded_at: string }[]
  safe_actions: string[]
}
export interface EvidenceResult { evidence: PaymentEvidence; ai_status: 'available' | 'unavailable'; model_selection: { fact_codes: string[]; action_codes: string[] } | null }
const states = new Set(['PENDING', 'CREATION_UNCERTAIN', 'CREATED', 'APPROVED', 'CAPTURING', 'CAPTURE_PENDING', 'CAPTURE_UNCERTAIN', 'COMPLETED', 'FAILED', 'VOIDED'])
const factCodes = new Set(['STORED_STATE', 'FRESHNESS_UNKNOWN', 'CANCEL_NOT_VOID', 'RECORDED_CAPTURE', 'MISSING_CAPTURE', 'NOT_CONFIRMED_PAID'])
const eventCodes = new Set(['RECORD_CREATED', 'ORDER_CREATED', 'APPROVAL_OBSERVED', 'CAPTURE_STARTED', 'CAPTURE_COMPLETED', 'CAPTURE_PENDING', 'CAPTURE_UNCERTAIN', 'CAPTURE_LEASE_EXPIRED', 'LEGACY_REVERIFICATION_REQUIRED'])
function obj(value: unknown): Record<string, unknown> { if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid evidence'); return value as Record<string, unknown> }
function str(value: unknown): string { if (typeof value !== 'string' || !value || value.length > 500) throw new Error('Invalid evidence'); return value }
function date(value: unknown): string { const text = str(value); if (!Number.isFinite(Date.parse(text))) throw new Error('Invalid date'); return text }
function state(value: unknown): PaymentStatus { const text = str(value); if (!states.has(text)) throw new Error('Invalid state'); return text as PaymentStatus }
function codes(value: unknown, allowed: Set<string>, limit: number): string[] { if (!Array.isArray(value) || value.length > limit || value.some((v) => typeof v !== 'string' || !allowed.has(v)) || new Set(value).size !== value.length) throw new Error('Invalid codes'); return value as string[] }
export function parseEvidence(value: unknown): EvidenceResult {
  const body = obj(value); const raw = obj(body.evidence)
  if (raw.source !== 'stored_backend_record' || raw.provider_freshness !== 'not_checked' || raw.current_provider_state_verified !== false || typeof raw.uncertain !== 'boolean' || typeof raw.events_truncated !== 'boolean' || !Array.isArray(raw.facts) || raw.facts.length > 8 || !Array.isArray(raw.events) || raw.events.length > 50) throw new Error('Invalid evidence')
  const facts = raw.facts.map((v) => { const f = obj(v); const code = str(f.code); if (!factCodes.has(code)) throw new Error('Invalid fact'); return { code, text: str(f.text) } })
  const evidence: PaymentEvidence = { state: state(raw.state), amount: parseMoney(raw.amount), observed_at: date(raw.observed_at), record_updated_at: date(raw.record_updated_at), uncertain: raw.uncertain, events_truncated: raw.events_truncated, facts, safe_actions: codes(raw.safe_actions, new Set(Object.keys(actionLabels)), 4), events: raw.events.map((v) => { const e = obj(v); const code = str(e.code); if (!eventCodes.has(code)) throw new Error('Invalid event'); return { code, state: e.state === null ? null : state(e.state), recorded_at: date(e.recorded_at) } }) }
  if (body.ai_status === 'unavailable' && body.model_selection === null) return { evidence, ai_status: 'unavailable', model_selection: null }
  if (body.ai_status !== 'available') throw new Error('Invalid AI status')
  const plan = obj(body.model_selection)
  const selection = { fact_codes: codes(plan.fact_codes, new Set(facts.map((f) => f.code)), 8), action_codes: codes(plan.action_codes, new Set(evidence.safe_actions), 4) }
  if (!selection.fact_codes.length) throw new Error('Empty model selection')
  return { evidence, ai_status: 'available', model_selection: selection }
}
export async function loadEvidence(orderId: string, signal: AbortSignal, fetcher: typeof fetch = fetch): Promise<EvidenceResult> {
  if (!isOrderId(orderId)) throw new Error('Invalid order identity')
  const abort = new AbortController(); const cancel = () => abort.abort()
  signal.throwIfAborted(); signal.addEventListener('abort', cancel, { once: true })
  const timer = setTimeout(cancel, 25000)
  try {
    const headers: Record<string, string> = { Accept: 'application/json' }
    const env = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env ?? {}
    const token = env.VITE_LOCAL_EVIDENCE_TOKEN
    const user = env.VITE_LOCAL_EVIDENCE_USER_ID
    if (token && user) { headers.Authorization = `Bearer ${token}`; headers['X-RescuePay-Local-User'] = user }
    const response = await fetcher(`/api/v1/payments/orders/${orderId}/evidence`, { method: 'GET', credentials: 'omit', cache: 'no-store', redirect: 'error', headers, signal: abort.signal })
    if (!response.ok || !/^application\/json(?:;|$)/i.test(response.headers.get('content-type') ?? '')) throw new Error('Evidence unavailable')
    return parseEvidence(await response.json())
  } finally { clearTimeout(timer); signal.removeEventListener('abort', cancel) }
}
