import { PaymentExplanation } from './PaymentExplanation'
import type { useSandboxCheckout } from '../hooks/useSandboxCheckout'
import type { CheckoutPhase } from '../checkout/controller'
import './SandboxCheckout.css'

const titles: Record<CheckoutPhase, string> = {
  loading: 'Loading demo catalog', ready: 'Ready to prepare a Sandbox order', creating: 'Creating order',
  'awaiting-approval': 'Buyer approval / capture required', checking: 'Checking backend status', capturing: 'Capture in progress',
  cancelled: 'Approval cancelled', pending: 'Payment processing — not paid', failed: 'Payment not confirmed',
  completed: 'Sandbox capture verified', uncertain: 'Outcome uncertain — do not retry capture', error: 'Checkout needs attention',
}

export function SandboxCheckout({ checkout }: { checkout: ReturnType<typeof useSandboxCheckout> }) {
  const { state, controller } = checkout
  const op = state.operation
  const configured = controller.configured()
  const canApprove = !!op?.approvalUrl && !op.captureAttempted && ['awaiting-approval', 'cancelled'].includes(state.phase)
  const payment = state.payment

  return (
    <section className="panel sandbox-checkout" aria-labelledby="sandbox-checkout-title" aria-busy={state.busy}>
      <div className="sandbox-heading"><div><span className="mini-eyebrow">BACKEND-PRICED DEMO CATALOG</span><h2 id="sandbox-checkout-title">Sandbox demo checkout</h2></div><span className="badge">Test funds only</span></div>
      <p>Choose a fixed USD demo item, approve on PayPal Sandbox, then verify capture with the backend. These items are demo fixtures, not production merchant pricing.</p>

      <div className="sandbox-configuration">
        <strong>{configured ? 'Local checkout configuration is available' : 'Sandbox setup is incomplete'}</strong>
        <p>{controller.configurationMessage()}</p>
        <p>Backend health and local configuration checks do not verify PayPal connectivity or payment success.</p>
        <button className="text-button" disabled={state.busy} onClick={() => { void controller.start() }}>Recheck checkout configuration</button>
      </div>

      <form onSubmit={(event) => { event.preventDefault(); void controller.create() }}>
        <fieldset disabled={state.busy || !!op}>
          <legend>Choose a demo item</legend>
          <div className="sandbox-catalog">
            {state.catalog?.items.map((item) => <label className={`sandbox-item ${state.selectedItemId === item.item_id ? 'selected' : ''}`} key={item.item_id}>
              <input type="radio" name="sandbox-item" value={item.item_id} checked={state.selectedItemId === item.item_id} onChange={() => controller.choose(item.item_id)} />
              <span><strong>{item.name}</strong><span className="sandbox-item-id">{item.item_id}</span></span><span className="sandbox-price">USD {item.amount.value}</span>
            </label>)}
          </div>
        </fieldset>
        {state.catalog && state.catalog.items.length === 0 && <p>No demo items are available. No checkout can be started.</p>}
        {!op?.orderId && <button className="button" type="submit" disabled={state.busy || !configured || !state.selectedItemId || state.storageProblem}>
          {op && state.phase !== 'ready' ? 'Recover / retry same checkout' : 'Create Sandbox order'}
        </button>}
      </form>

      <div className={`sandbox-result phase-${state.phase}`} role="status" aria-live="polite" aria-atomic="true">
        <h3>{titles[state.phase]}</h3><p>{state.message}</p>
      </div>

      {op && <dl className="sandbox-details">
        <div><dt>Demo item</dt><dd>{op.itemId} · USD {op.amount.value}</dd></div>
        <div><dt>Creation operation ID</dt><dd>{op.key}</dd></div>
        {op.orderId && <div><dt>PayPal order</dt><dd>{op.orderId}</dd></div>}
        {payment && <><div><dt>Backend payment state</dt><dd>{payment.status}</dd></div>{payment.capture_id && <div><dt>Verified capture ID</dt><dd>{payment.capture_id}</dd></div>}</>}
      </dl>}
      {payment && 'provider_refreshed' in payment && <p className="sandbox-provenance">{payment.provider_refreshed ? 'Provider identity and amount were checked during this lookup. Approval or a pending result is still not paid.' : 'This response uses the stored backend record; it does not claim a fresh provider lookup.'}</p>}

      <div className="sandbox-actions">
        {canApprove && <button className="button" disabled={state.busy || !configured} onClick={controller.approve}>{state.phase === 'cancelled' ? 'Resume approval on PayPal Sandbox' : 'Continue to PayPal Sandbox'}</button>}
        {controller.canCapture() && <button className="button" onClick={() => { void controller.captureApproved() }}>Capture approved Sandbox order</button>}
        {op?.orderId && <button className="sandbox-secondary" disabled={state.busy} onClick={() => { void controller.refresh() }}>Check backend payment status</button>}
        {op && controller.canStartNew() && <button className="sandbox-secondary" onClick={controller.newCheckout}>Explicitly start a new checkout</button>}
      </div>
      {op?.orderId && <PaymentExplanation key={op.orderId} orderId={op.orderId} />}
      <p className="sandbox-footnote">Approval opens in this same tab. Session storage retains this operation across the return/cancel redirect. A redirect, HTTP 200, approval, or processing state never counts as payment confirmation.</p>
    </section>
  )
}
