import { useEffect, useState, useId } from 'react'
import { actionLabels, loadEvidence, type EvidenceResult } from '../api/evidence'

export function PaymentExplanation({ orderId }: { orderId: string }) {
  const titleId = useId()
  const [result, setResult] = useState<{ orderId: string; revision: number; data: EvidenceResult | null; error: boolean } | null>(null)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    const abort = new AbortController(); let active = true
    void loadEvidence(orderId, abort.signal).then((data) => { if (active) setResult({ orderId, revision, data, error: false }) }).catch(() => { if (active) setResult({ orderId, revision, data: null, error: true }) })
    return () => { active = false; abort.abort() }
  }, [orderId, revision])
  const current = result?.orderId === orderId && result.revision === revision ? result : null
  const data = current?.data
  const busy = current === null
  const error = current?.error
  return <section className="sandbox-configuration" aria-labelledby={titleId} aria-busy={busy}>
    <h3 id={titleId}>Payment evidence and explanation</h3>
    <p>Read-only stored evidence. Loading this panel never refreshes PayPal or performs a payment action.</p>
    {busy && <p role="status">Loading stored evidence…</p>}
    {error && <p role="status">Evidence unavailable. This endpoint requires explicit local development configuration. Payment status above remains separate.</p>}
    {data && <>
      <h4>Backend facts (not AI)</h4>
      <p>Stored state: {data.evidence.state} · {data.evidence.amount.currency_code} {data.evidence.amount.value}</p>
      <p>Record updated: {data.evidence.record_updated_at}. Snapshot: {data.evidence.observed_at}. Current provider state not checked.</p>
      {data.evidence.uncertain && <p><strong>Uncertain evidence: reconcile before any new payment action.</strong></p>}
      <ul>{data.evidence.facts.map((fact) => <li key={fact.code}>{fact.text}</li>)}</ul>
      <h4>Backend-owned safe suggestions</h4>
      <ul>{data.evidence.safe_actions.map((code) => <li key={code}>{actionLabels[code]}</li>)}</ul>
      <h4>Sanitized stored audit events</h4>
      {!data.evidence.events.length && <p>No allowlisted events in this snapshot.</p>}
      <ul>{data.evidence.events.map((event, index) => <li key={index}>{event.recorded_at} — {event.code}{event.state ? ` (${event.state})` : ''}</li>)}</ul>
      {data.evidence.events_truncated && <p>Only the latest event window is included.</p>}
      <h4>AI explanation</h4>
      {data.ai_status === 'unavailable' ? <p>AI explanation unavailable. Backend facts and rule-based suggestions above remain usable.</p> : <><p>The model prioritizes relevant fact and action IDs. The wording below is backend-authored, not model-generated prose; the model cannot change payment truth.</p><ul>{data.model_selection?.fact_codes.map((code) => <li key={code}>{data.evidence.facts.find((fact) => fact.code === code)?.text}</li>)}</ul><p>Model-selected suggestions: {data.model_selection?.action_codes.map((code) => actionLabels[code]).join(' ')}</p></>}
    </>}
    <button className="text-button" disabled={busy} onClick={() => setRevision((value) => value + 1)}>Reload stored evidence</button>
  </section>
}
