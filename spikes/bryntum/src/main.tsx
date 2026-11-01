import { useMemo } from 'react'
import { BryntumScheduler } from '@bryntum/scheduler-react'
import { projectTimeline, syntheticRecords } from './timeline-model.mjs'
import './styles.css'

export function PaymentRecoveryTimeline() {
  const records = useMemo(() => projectTimeline(syntheticRecords), [])
  const start = new Date('2026-10-31T00:00:00Z')
  const end = new Date('2026-11-03T00:00:00Z')
  const resources = records.map((record) => ({ id: record.id, name: `${record.name} · ${record.state}` }))
  const events = records.flatMap((record) => record.audit.map((event, index) => ({ id: `${record.id}-${index}`, resourceId: record.id, name: `${event.code} · ${record.safeAction}`, startDate: new Date(event.recorded_at), endDate: new Date(new Date(event.recorded_at).getTime() + 30 * 60 * 1000), readOnly: true })))
  return <main className="spike-shell">
    <h1>Payment Recovery Timeline</h1>
    <p className="synthetic-label">SYNTHETIC/DEMO EVIDENCE ONLY — read-only investigation spike</p>
    <p>Backend state and evidence freshness are authoritative. This timeline cannot capture, refund, edit amounts, refresh PayPal, or declare payment success.</p>
    <section className="timeline-summary" aria-label="Timeline summary">
      {records.map((record) => <article key={record.id}><strong>{record.id}</strong><span>State: {record.state}</span><span>Freshness: {record.freshness}</span><span>{record.uncertain ? 'Uncertain' : 'Certain'} · action: {record.safeAction}</span><span>Deadline: {record.deadline}</span></article>)}
    </section>
    <div className="timeline-frame" aria-label="Payment audit event timeline">
      <BryntumScheduler startDate={start} endDate={end} viewPreset="hourAndDay" resources={resources} events={events} readOnly />
    </div>
  </main>
}

export default PaymentRecoveryTimeline
