import test from 'node:test'
import assert from 'node:assert/strict'
import { parseEvidence, loadEvidence } from '../src/api/evidence.ts'
const payload = () => ({ evidence: { state: 'CAPTURE_UNCERTAIN', amount: { currency_code: 'USD', value: '1.00' }, observed_at: '2026-10-31T00:00:00Z', record_updated_at: '2026-10-28T00:00:00Z', source: 'stored_backend_record', provider_freshness: 'not_checked', current_provider_state_verified: false, uncertain: true, events_truncated: false, facts: [{ code: 'FRESHNESS_UNKNOWN', text: 'Stored evidence only.' }], events: [], safe_actions: ['CHECK_STATUS', 'MANUAL_RECONCILIATION'] }, ai_status: 'unavailable', model_selection: null })
test('unconfigured AI preserves usable uncertain/stale stored facts', () => {
  const result = parseEvidence(payload())
  assert.equal(result.ai_status, 'unavailable'); assert.equal(result.evidence.uncertain, true)
  assert.equal(result.evidence.record_updated_at, '2026-10-28T00:00:00Z')
  assert.equal(result.model_selection, null)
})
test('invalid model claims/actions and fake freshness fail closed', () => {
  for (const plan of [{ fact_codes: ['PAID'], action_codes: [] }, { fact_codes: ['FRESHNESS_UNKNOWN'], action_codes: ['CAPTURE'] }, { fact_codes: [], action_codes: [] }]) {
    assert.throws(() => parseEvidence({ ...payload(), ai_status: 'available', model_selection: plan }))
  }
  const value = payload(); value.evidence.current_provider_state_verified = true
  assert.throws(() => parseEvidence(value))
})
test('structured model selection can reference only backend-owned facts and actions', () => {
  const value = { ...payload(), ai_status: 'available', model_selection: { fact_codes: ['FRESHNESS_UNKNOWN'], action_codes: ['CHECK_STATUS'] } }
  assert.equal(parseEvidence(value).model_selection.fact_codes[0], 'FRESHNESS_UNKNOWN')
})
test('read-only adapter uses GET with no credentials; never payment endpoints', async () => {
  const calls = []
  const result = await loadEvidence('TESTORDER12345', new AbortController().signal, async (url, init) => { calls.push({ url, init }); return new Response(JSON.stringify(payload()), { headers: { 'Content-Type': 'application/json' } }) })
  assert.equal(result.ai_status, 'unavailable'); assert.equal(calls.length, 1)
  assert.equal(calls[0].url, '/api/v1/payments/orders/TESTORDER12345/evidence')
  assert.equal(calls[0].init.method, 'GET'); assert.equal(calls[0].init.credentials, 'omit')
})
test('disabled/HTML endpoints and cancelled requests do not fabricate AI/facts', async () => {
  await assert.rejects(loadEvidence('TESTORDER12345', new AbortController().signal, async () => new Response('<html>', { headers: { 'Content-Type': 'text/html' } })))
  await assert.rejects(loadEvidence('TESTORDER12345', new AbortController().signal, async () => new Response('{}', { status: 404 })))
  const abort = new AbortController(); abort.abort()
  await assert.rejects(loadEvidence('TESTORDER12345', abort.signal, async () => { assert.fail('must not request') }))
})
