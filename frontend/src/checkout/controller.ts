import {
  CheckoutApiError, isItemId, isOrderId, isUuid, parseMoney, safeSandboxApproval,
  type CheckoutApi, type DemoCatalog, type Money, type PaymentRecord, type VerifiedPayment,
} from '../api/checkout.ts'

export const CHECKOUT_STORAGE_KEY = 'rescuepay.sandbox.checkout.v1'
export type CheckoutPhase = 'loading' | 'ready' | 'creating' | 'awaiting-approval' | 'checking' | 'capturing' | 'cancelled' | 'pending' | 'failed' | 'completed' | 'uncertain' | 'error'
export interface CheckoutOperation {
  version: 1; key: string; itemId: string; amount: Money
  orderId?: string; paymentId?: string; approvalUrl?: string
  captureAttempted: boolean; returned: boolean; cancelled: boolean
}
export interface CheckoutState {
  phase: CheckoutPhase; busy: boolean; message: string; catalog: DemoCatalog | null
  selectedItemId: string; operation: CheckoutOperation | null
  payment: VerifiedPayment | PaymentRecord | null; storageProblem: boolean
}
export interface CheckoutDependencies {
  api: CheckoutApi
  storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>
  location: () => { origin: string; pathname: string; search: string }
  redirect: (url: string) => void
  clearCallback: () => void
  uuid: () => string
}

function restoreOperation(raw: string | null): CheckoutOperation | null {
  if (raw === null) return null
  if (raw.length > 4096) throw new Error('invalid saved operation')
  const op = JSON.parse(raw) as Record<string, unknown>
  if (!op || op.version !== 1 || !isUuid(op.key) || !isItemId(op.itemId) || typeof op.captureAttempted !== 'boolean' || typeof op.returned !== 'boolean' || typeof op.cancelled !== 'boolean') throw new Error('invalid saved operation')
  const hasOrder = op.orderId !== undefined
  if (hasOrder ? !isOrderId(op.orderId) || !isUuid(op.paymentId) : op.paymentId !== undefined || op.captureAttempted || op.returned) throw new Error('invalid saved identity')
  if (op.approvalUrl !== undefined && (!hasOrder || !safeSandboxApproval(op.approvalUrl, op.orderId as string))) throw new Error('invalid saved approval')
  return { version: 1, key: op.key, itemId: op.itemId, amount: parseMoney(op.amount), orderId: op.orderId as string | undefined, paymentId: op.paymentId as string | undefined, approvalUrl: op.approvalUrl as string | undefined, captureAttempted: op.captureAttempted, returned: op.returned, cancelled: op.cancelled }
}

export class CheckoutController {
  private deps: CheckoutDependencies
  private state: CheckoutState
  private listeners = new Set<() => void>()
  private generation = 0
  private active = false
  private abort = new AbortController()

  constructor(deps: CheckoutDependencies) {
    this.deps = deps
    let operation: CheckoutOperation | null = null
    let storageProblem = false
    try { operation = restoreOperation(deps.storage.getItem(CHECKOUT_STORAGE_KEY)) } catch { storageProblem = true }
    this.state = { phase: 'loading', busy: false, message: '', catalog: null, selectedItemId: operation?.itemId ?? '', operation, payment: null, storageProblem }
  }
  getSnapshot = (): CheckoutState => this.state
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener) } }
  private set(patch: Partial<CheckoutState>) {
    this.state = { ...this.state, ...patch }
    this.listeners.forEach((listener) => listener())
  }
  private live(generation: number) { return this.active && generation === this.generation }
  private save(op: CheckoutOperation): boolean {
    try {
      this.deps.storage.setItem(CHECKOUT_STORAGE_KEY, JSON.stringify(op))
      this.set({ operation: op })
      return true
    } catch {
      this.set({ phase: 'error', busy: false, storageProblem: true, message: 'Session storage is unavailable. No further payment action will be sent. Restore storage access and reload to recover this checkout.' })
      return false
    }
  }
  configured(): boolean {
    return !!this.state.catalog?.checkout_available && this.state.catalog.return_origin === this.deps.location().origin && !this.state.storageProblem
  }
  configurationMessage(): string {
    if (!this.state.catalog) return 'Catalog configuration could not be loaded.'
    if (this.state.catalog.return_origin !== this.deps.location().origin) return 'Return/cancel URLs must use this exact frontend origin. Restart the backend after correcting its private configuration.'
    const messages: Record<string, string> = {
      SANDBOX_CHECKOUT_DISABLED: 'Sandbox checkout is disabled in backend configuration.',
      PAYPAL_NOT_CONFIGURED: 'Private Sandbox client credentials are not configured.',
      MERCHANT_NOT_CONFIGURED: 'The expected Sandbox merchant ID is not configured.',
      DATABASE_NOT_READY: 'The checkout database schema is not ready.',
      RETURN_URLS_INVALID: 'Backend return/cancel URLs do not match the supported local handlers.',
    }
    return this.state.catalog.blocking_reasons.map((reason) => messages[reason] ?? 'Backend setup is incomplete.').join(' ') || 'Sandbox checkout is configured locally; provider connectivity is not yet verified.'
  }
  stop = () => { this.active = false; this.generation += 1; this.abort.abort() }

  start = async (): Promise<void> => {
    this.abort.abort()
    this.abort = new AbortController()
    const generation = ++this.generation
    this.active = true
    const currentLocation = this.deps.location()
    const location = { pathname: currentLocation.pathname, search: currentLocation.search }
    this.set({ busy: true, phase: 'loading', payment: null, message: 'Loading the backend-owned Sandbox demo catalog…' })
    try {
      const catalog = await this.deps.api.catalog(this.abort.signal)
      if (!this.live(generation)) return
      this.set({ catalog, selectedItemId: this.state.operation?.itemId ?? catalog.items[0]?.item_id ?? '' })
    } catch {
      if (!this.live(generation)) return
      this.set({ catalog: null, message: 'Could not load the demo catalog. Check the local backend configuration.' })
    }
    if (!this.live(generation)) return
    if (this.state.storageProblem) {
      this.set({ busy: false, phase: 'error', message: 'Saved checkout identity is invalid or session storage is unavailable. Do not start another payment; restore the session or reconcile the prior operation first.' })
      return
    }
    let op = this.state.operation
    const callback = location.pathname === '/payment/return' ? 'return' : location.pathname === '/payment/cancel' ? 'cancel' : null
    if (callback) {
      const tokens = new URLSearchParams(location.search).getAll('token')
      if (!op?.orderId || tokens.length > 1 || (callback === 'return' && tokens.length !== 1) || (tokens.length === 1 && tokens[0] !== op.orderId)) {
        this.set({ busy: false, phase: 'error', message: 'The redirect does not match the saved checkout. No capture was requested. Recover the original operation; a redirect token alone is not payment evidence.' })
        return
      }
      op = { ...op, returned: callback === 'return', cancelled: callback === 'cancel' }
      if (!this.save(op)) return
      this.deps.clearCallback()
    }
    if (op?.orderId) await this.readStatus(generation, true)
    else if (op) this.set({ busy: false, phase: 'uncertain', message: 'A saved creation operation has no verified order response. Recover it using the same operation key; do not start a duplicate checkout.' })
    else this.set({ busy: false, phase: this.state.catalog ? 'ready' : 'error', message: this.state.catalog ? 'Choose a demo item. Prices are resolved by the backend; only Sandbox test funds are used.' : 'The catalog is unavailable. No payment request has been made.' })
  }

  choose = (itemId: string) => {
    if (!this.state.busy && !this.state.operation && this.state.catalog?.items.some((item) => item.item_id === itemId)) this.set({ selectedItemId: itemId })
  }
  canStartNew(): boolean {
    const { operation, payment, phase } = this.state
    // An HTTP error is not evidence that replacing this payment is safe.
    const terminal = !!payment && ['COMPLETED', 'FAILED', 'VOIDED'].includes(payment.status)
    const cancelledBeforeCapture = phase === 'cancelled' && !operation?.captureAttempted && !!payment && ['CREATED', 'APPROVED'].includes(payment.status)
    return !this.state.busy && this.configured() && (!operation || terminal || cancelledBeforeCapture)
  }
  newCheckout = () => {
    if (!this.canStartNew()) return
    try { this.deps.storage.removeItem(CHECKOUT_STORAGE_KEY) } catch {
      this.set({ phase: 'error', storageProblem: true, message: 'The saved operation could not be replaced. Restore session storage before starting another checkout.' })
      return
    }
    this.set({ operation: null, payment: null, phase: 'ready', message: 'Choose a demo item for an explicitly new checkout. Its key will be generated when you create the order.' })
  }
  private prepareOperation() {
    const item = this.state.catalog?.items.find((item) => item.item_id === this.state.selectedItemId)
    if (!item) return
    let key: string
    try { key = this.deps.uuid() } catch { this.set({ phase: 'error', message: 'A secure operation key could not be generated.' }); return }
    if (!isUuid(key)) return
    if (this.save({ version: 1, key, itemId: item.item_id, amount: { ...item.amount }, captureAttempted: false, returned: false, cancelled: false })) {
      this.set({ phase: 'ready', payment: null, message: 'A new checkout operation is prepared. Create its Sandbox order when ready.' })
    }
  }
  create = async (): Promise<void> => {
    if (!this.active || this.state.busy || !this.configured() || this.state.operation?.orderId) return
    if (!this.state.operation) this.prepareOperation()
    const op = this.state.operation
    if (!op || this.state.storageProblem) return
    const generation = this.generation
    this.set({ phase: 'creating', busy: true, message: 'Creating a Sandbox order using the saved operation key…' })
    try {
      const result = await this.deps.api.create(op.itemId, op.key, this.abort.signal)
      if (!this.live(generation)) return
      const saved = { ...op, orderId: result.order_id, paymentId: result.payment_id, approvalUrl: result.approval_url }
      if (!this.save(saved)) return
      if (['CREATED', 'APPROVED'].includes(result.status)) {
        this.set({ phase: 'awaiting-approval', busy: false, message: 'Order created. Continue to PayPal Sandbox to approve. No payment success has been confirmed.' })
      } else await this.readStatus(generation, false)
    } catch (error) {
      if (!this.live(generation) || this.state.storageProblem) return
      const code = error instanceof CheckoutApiError ? error.code : 'NETWORK'
      const unavailable = ['SANDBOX_CHECKOUT_UNAVAILABLE', 'PAYPAL_NOT_CONFIGURED', 'PAYABLES_NOT_CONFIGURED', 'PAYMENT_VALIDATION_FAILED', 'REQUEST_VALIDATION_ERROR'].includes(code)
      this.set({ busy: false, phase: unavailable ? 'error' : 'uncertain', message: unavailable ? 'Backend setup or item validation prevented checkout. Recheck configuration, then retry this same operation.' : 'Order creation could not be verified. Recover using the same operation key. Do not create another order or infer success.' })
    }
  }
  approve = () => {
    const op = this.state.operation
    if (!this.active || this.state.busy || !this.configured() || !op?.orderId || op.captureAttempted || !op.approvalUrl) return
    const safe = safeSandboxApproval(op.approvalUrl, op.orderId)
    if (!safe) { this.set({ phase: 'error', message: 'The approval destination is invalid. No redirect or capture was requested.' }); return }
    if (!this.save({ ...op, cancelled: false, returned: false })) return
    try { this.deps.redirect(safe) } catch { this.set({ message: 'Navigation was blocked. The saved checkout is unchanged; use Continue to PayPal Sandbox again.' }) }
  }

  private matches(payment: VerifiedPayment | PaymentRecord): boolean {
    const op = this.state.operation
    return !!op && payment.order_id === op.orderId && payment.payment_id === op.paymentId && payment.amount.currency_code === op.amount.currency_code && payment.amount.value === op.amount.value && (!('reference_id' in payment) || payment.reference_id === op.itemId)
  }
  private applyPayment(payment: VerifiedPayment | PaymentRecord) {
    if (!this.matches(payment)) throw new CheckoutApiError('INVALID_IDENTITY')
    const op = this.state.operation
    this.set({ payment, busy: false })
    if (payment.status === 'COMPLETED' && payment.capture_id) this.set({ phase: 'completed', message: 'The backend verified a completed Sandbox capture. These are test funds, not a real payment.' })
    else if (['FAILED', 'VOIDED'].includes(payment.status)) this.set({ phase: 'failed', message: 'The backend reports this order failed or was voided. No payment success is confirmed.' })
    else if (['CAPTURING', 'CAPTURE_PENDING'].includes(payment.status)) this.set({ phase: 'pending', message: 'Payment is processing. It is not confirmed paid. Check backend status later; do not send another capture.' })
    else if (['CAPTURE_UNCERTAIN', 'CREATION_UNCERTAIN', 'PENDING'].includes(payment.status) || op?.captureAttempted) this.set({ phase: 'uncertain', message: 'The capture outcome is uncertain. Do not retry capture or start a duplicate payment. Check backend status to reconcile.' })
    else if (op?.cancelled) this.set({ phase: 'cancelled', message: 'Approval was cancelled in this browser. This redirect does not void the provider order or prove a payment outcome. No capture was requested here.' })
    else this.set({ phase: 'awaiting-approval', message: payment.status === 'APPROVED' ? 'The backend observed buyer approval. It is not paid; capture still requires backend verification.' : 'The order is awaiting buyer approval. No payment success is confirmed.' })
  }
  private async readStatus(generation: number, allowReturnCapture: boolean): Promise<void> {
    const op = this.state.operation
    if (!op?.orderId) return
    this.set({ busy: true, phase: 'checking', payment: null, message: 'Checking the saved order with the backend…' })
    try {
      const payment = await this.deps.api.status(op.orderId, this.abort.signal)
      if (!this.live(generation)) return
      this.applyPayment(payment)
      if (allowReturnCapture && this.state.operation?.returned && !this.state.operation.cancelled && this.canCapture()) await this.captureApproved()
    } catch {
      if (this.live(generation)) this.set({ busy: false, phase: 'uncertain', message: 'Backend status could not be verified for this saved order. Keep its identity and check again; no success or safe retry is established.' })
    }
  }
  refresh = async (): Promise<void> => {
    if (this.active && !this.state.busy && this.state.operation?.orderId) await this.readStatus(this.generation, false)
  }
  canCapture(): boolean {
    const op = this.state.operation
    const payment = this.state.payment
    return !this.state.busy && this.configured() && !!op?.orderId && !op.captureAttempted && !op.cancelled && payment?.status === 'APPROVED' && 'provider_refreshed' in payment && payment.provider_refreshed === true
  }
  captureApproved = async (): Promise<void> => {
    if (!this.active || !this.canCapture()) return
    const op = this.state.operation
    if (!op?.orderId || !this.save({ ...op, captureAttempted: true })) return
    const generation = this.generation
    this.set({ busy: true, phase: 'capturing', message: 'Capturing the approved Sandbox order. A timeout will be treated as uncertain, not retried.' })
    try {
      const payment = await this.deps.api.capture(op.orderId, this.abort.signal)
      if (this.live(generation)) this.applyPayment(payment)
    } catch (error) {
      if (!this.live(generation)) return
      const code = error instanceof CheckoutApiError ? error.code : 'NETWORK'
      const rejected = ['ORDER_NOT_APPROVED', 'PAYMENT_INSTRUMENT_DECLINED', 'PAYMENT_INVALID_STATE', 'AMOUNT_MISMATCH', 'PAYMENT_VERIFICATION_FAILED'].includes(code)
      this.set({ busy: false, phase: rejected ? 'failed' : 'uncertain', message: rejected ? 'The backend refused or declined this capture. No success is confirmed. Check the saved order before choosing another checkout.' : 'Capture outcome could not be verified. Do not retry capture. Check backend status using this saved order.' })
    }
  }
}
