import { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { BryntumScheduler } from '@bryntum/scheduler-react'
import { isTimelineEnabled, projectTimeline, syntheticRecords } from './timeline-model.mjs'
import './styles.css'

type TimelineAudit = { recorded_at: string; code: string }
type TimelineRow = { id: string; name: string; state: string; amount: string; currency: string; freshness: string; uncertain: boolean; deadline: string; safeAction: string; audit: TimelineAudit[] }

export function PaymentRecoveryTimeline() {
  const enabled = isTimelineEnabled(import.meta.env.VITE_BRYNTUM_TIMELINE_ENABLED)
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState(false)
  useEffect(() => {
    if (!enabled) return
    const timer = window.setTimeout(() => setLoading(false), 120)
    return () => window.clearTimeout(timer)
  }, [enabled])
  const records = useMemo<TimelineRow[]>(() => projectTimeline(syntheticRecords) as TimelineRow[], [])
  const start = new Date('2026-10-31T00:00:00Z')
  const end = new Date('2026-11-03T00:00:00Z')
  const resources = records.map((record) => ({ id: record.id, name: `${record.name} · ${record.state}` }))
  const events = records.flatMap((record) => record.audit.map((event, index) => ({ id: `${record.id}-${index}`, resourceId: record.id, name: `${event.code} · ${record.safeAction}`, startDate: new Date(event.recorded_at), endDate: new Date(new Date(event.recorded_at).getTime() + 30 * 60 * 1000), readOnly: true })))
  if (!enabled) return <main className="spike-shell" role="status"><h1>Payment Recovery Timeline</h1><p className="synthetic-label">OPTIONAL FEATURE DISABLED</p><p>Bryntum licence access is not confirmed. The normal RescuePay application remains available without this component.</p></main>
  if (loading) return <main className="spike-shell" aria-busy="true"><h1>Payment Recovery Timeline</h1><p role="status">Loading synthetic evidence…</p></main>
  if (error) return <main className="spike-shell"><h1>Payment Recovery Timeline</h1><p role="alert">Timeline unavailable. No payment state was changed.</p><button type="button" onClick={() => { setError(false); setLoading(true) }}>Retry local timeline</button></main>
  if (!records.length) return <main className="spike-shell"><h1>Payment Recovery Timeline</h1><p role="status">No permitted synthetic/demo evidence is available.</p></main>
  return <main className="spike-shell">
    <h1>Payment Recovery Timeline</h1>
    <p className="synthetic-label">SYNTHETIC/DEMO EVIDENCE ONLY — read-only investigation spike</p>
    <p>Backend state and evidence freshness are authoritative. This timeline cannot capture, refund, edit amounts, refresh PayPal, or declare payment success.</p>
    <section className="timeline-summary" aria-label="Timeline summary">
      {records.map((record) => <article key={record.id}><strong>{record.id}</strong><span>State: {record.state}</span><span>Amount: {record.currency} {record.amount}</span><span>Freshness: {record.freshness}</span><span>{record.uncertain ? 'Uncertain' : 'Certain'} · action: {record.safeAction}</span><span>Deadline: {record.deadline}</span></article>)}
    </section>
    <div className="timeline-frame" aria-label="Payment audit event timeline">
      <BryntumScheduler startDate={start} endDate={end} viewPreset="hourAndDay" resources={resources} events={events} readOnly aria-label="Read-only synthetic payment audit events" />
    </div>
  </main>
}

export default PaymentRecoveryTimeline

const root = document.getElementById('root')
if (root) createRoot(root).render(<PaymentRecoveryTimeline />)
