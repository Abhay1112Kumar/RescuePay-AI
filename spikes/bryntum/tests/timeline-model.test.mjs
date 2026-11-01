import test from 'node:test'
import assert from 'node:assert/strict'
import { projectTimeline } from '../src/timeline-model.mjs'

const base = (overrides = {}) => ({ owner_id: 'demo-merchant', reference_namespace: 'synthetic', reference: 'SYNTH-001', state: 'CAPTURE_UNCERTAIN', freshness: 'stale', uncertain: true, reconciliation_deadline: '2026-11-01T12:00:00Z', safe_action: 'MANUAL_RECONCILIATION', audit: [{ recorded_at: '2026-10-31T02:00:00Z', code: 'CAPTURE_UNCERTAIN' }, { recorded_at: '2026-10-31T01:00:00Z', code: 'RECORD_CREATED' }], ...overrides })

test('projects only owned synthetic/demo records and redacts other namespaces', () => {
  const rows = projectTimeline([base(), base({ reference_namespace: 'paypal', reference: 'raw-provider' }), base({ owner_id: 'other-user', reference: 'other-owner' })])
  assert.deepEqual(rows.map((row) => row.id), ['SYNTH-001'])
  assert.equal(rows[0].name.includes('synthetic/demo'), true)
})

test('orders audit events and preserves uncertain/stale markers', () => {
  const [row] = projectTimeline([base()])
  assert.deepEqual(row.audit.map((event) => event.code), ['RECORD_CREATED', 'CAPTURE_UNCERTAIN'])
  assert.equal(row.uncertain, true)
  assert.equal(row.freshness, 'STALE')
  assert.equal(row.safeAction, 'MANUAL_RECONCILIATION')
})

test('invalid state/action fall back to safe read-only display values', () => {
  const [row] = projectTimeline([base({ state: 'PAID', safe_action: 'CAPTURE' })])
  assert.equal(row.state, 'STALE')
  assert.equal(row.safeAction, 'REVIEW_RECORD')
})
