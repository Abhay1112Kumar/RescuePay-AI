const ALLOWED_STATES = new Set(['CREATED', 'APPROVED', 'CAPTURING', 'COMPLETED', 'CANCELLED', 'CAPTURE_UNCERTAIN', 'STALE'])
const ALLOWED_ACTIONS = new Set(['REVIEW_RECORD', 'CHECK_STATUS', 'MANUAL_RECONCILIATION', 'WAIT'])

export function projectTimeline(records) {
  return records
    .filter((record) => (record.reference_namespace === 'synthetic' || record.reference_namespace === 'demo') && record.owner_id === 'demo-merchant')
    .map((record) => {
      const state = ALLOWED_STATES.has(record.state) ? record.state : 'STALE'
      const safeAction = ALLOWED_ACTIONS.has(record.safe_action) ? record.safe_action : 'REVIEW_RECORD'
      return {
        id: record.reference,
        name: `${record.reference} — synthetic/demo evidence`,
        state,
        freshness: record.freshness === 'stale' ? 'STALE' : 'NOT_CHECKED',
        uncertain: Boolean(record.uncertain),
        deadline: record.reconciliation_deadline,
        safeAction,
        audit: [...record.audit].sort((a, b) => a.recorded_at.localeCompare(b.recorded_at)),
      }
    })
}

export const syntheticRecords = [
  { owner_id: 'demo-merchant', reference_namespace: 'synthetic', reference: 'SYNTH-UNCERTAIN-001', state: 'CAPTURE_UNCERTAIN', freshness: 'stale', uncertain: true, reconciliation_deadline: '2026-11-01T12:00:00Z', safe_action: 'MANUAL_RECONCILIATION', audit: [{ recorded_at: '2026-10-31T10:00:00Z', code: 'RECORD_CREATED' }, { recorded_at: '2026-10-31T10:01:00Z', code: 'CAPTURE_UNCERTAIN' }] },
  { owner_id: 'demo-merchant', reference_namespace: 'demo', reference: 'DEMO-COMPLETED-001', state: 'COMPLETED', freshness: 'not_checked', uncertain: false, reconciliation_deadline: '2026-11-02T12:00:00Z', safe_action: 'REVIEW_RECORD', audit: [{ recorded_at: '2026-10-31T09:00:00Z', code: 'RECORD_CREATED' }, { recorded_at: '2026-10-31T09:02:00Z', code: 'CAPTURE_COMPLETED' }] },
  { owner_id: 'other-user', reference_namespace: 'synthetic', reference: 'SYNTH-OTHER-001', state: 'COMPLETED', freshness: 'not_checked', uncertain: false, reconciliation_deadline: '2026-11-02T12:00:00Z', safe_action: 'REVIEW_RECORD', audit: [] },
]
