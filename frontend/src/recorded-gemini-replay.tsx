// Isolated development entry. Never imported by the application or used as fallback.
import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { PaymentExplanation } from './components/PaymentExplanation'
import './components/SandboxCheckout.css'

export function Replay() {
  const [error, setError] = useState(false)
  return <main style={{ maxWidth: 900, margin: '20px auto', padding: 16, fontFamily: 'system-ui', lineHeight: 1.6 }}>
    <h1>Recorded real Gemini response — synthetic evidence, offline replay.</h1>
    <p>This is a saved snapshot, not a live browser-to-Gemini test. No Gemini or PayPal calls. All payment data below is synthetic.</p>
    <p>Gemini selected fact/action IDs. Backend-authored wording is displayed below. Reload repeats the same recorded snapshot.</p>
    <label><input type="checkbox" checked={error} onChange={event => setError(event.target.checked)} /> Simulate offline replay error</label>
    <PaymentExplanation orderId={error ? 'REPLAYERROR00001' : 'REPLAYRECORDED001'} />
  </main>
}
createRoot(document.getElementById('root')!).render(<Replay />)
