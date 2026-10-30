import { useEffect, useRef, useState } from 'react'
import { Icon, type IconName } from './components/Icon'
import { BackendHealthPanel } from './components/BackendHealthPanel'
import { useBackendHealth } from './hooks/useBackendHealth'
import type { BackendHealthState } from './api/health'
import './App.css'

type Page = 'Overview' | 'Transactions' | 'Integrations'
type Status = 'All transactions' | 'Successful' | 'Pending' | 'Failed'

const navigation: { page: Page; icon: IconName }[] = [
  { page: 'Overview', icon: 'grid' },
  { page: 'Transactions', icon: 'arrows' },
  { page: 'Integrations', icon: 'plug' },
]

const metrics: { label: string; icon: IconName; description: string; color: string }[] = [
  { label: 'Payment volume', icon: 'wallet', description: 'Total processed amount', color: 'purple' },
  { label: 'Successful payments', icon: 'check', description: 'Completed transactions', color: 'green' },
  { label: 'Payment completion', icon: 'chart', description: 'Completed payment share', color: 'blue' },
  { label: 'Pending payments', icon: 'clock', description: 'Awaiting a payment update', color: 'orange' },
]

function SetupChecklist() {
  return (
    <ol className="setup-list">
      <li>
        <span className="step-icon complete"><Icon name="check" /></span>
        <div><strong>Explore your dashboard</strong><p>Your frontend workspace is ready.</p><span className="step-label ready">Ready</span></div>
      </li>
      <li>
        <span className="step-icon"><Icon name="plug" /></span>
        <div><strong>Connect payment APIs</strong><p>Waiting for backend integration.</p><span className="step-label">Not connected</span></div>
      </li>
      <li>
        <span className="step-icon"><Icon name="lock" /></span>
        <div><strong>Enable checkout</strong><p>Available after payment verification.</p><span className="step-label">Locked</span></div>
      </li>
    </ol>
  )
}

function Transactions({ compact = false, onViewAll }: { compact?: boolean; onViewAll?: () => void }) {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState<Status>('All transactions')
  const searchRef = useRef<HTMLInputElement>(null)
  const hasFilter = query.trim().length > 0 || status !== 'All transactions'

  return (
    <section className="panel transactions-panel" aria-labelledby="transactions-title">
      <div className="panel-heading">
        <div><h2 id="transactions-title">{compact ? 'Recent transactions' : 'Transaction history'}</h2><p>A clear view of every payment.</p></div>
        {compact && <button className="text-button" onClick={onViewAll}>View all <Icon name="arrow-right" /></button>}
      </div>
      <div className="transaction-controls">
        <label className="search-field"><Icon name="search" /><input ref={searchRef} aria-label="Search transactions" placeholder="Search transactions…" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
        <label className="filter-select"><Icon name="filter" /><span className="sr-only">Filter transactions by status</span><select aria-label="Filter transactions by status" value={status} onChange={(event) => setStatus(event.target.value as Status)}>
          {(['All transactions', 'Successful', 'Pending', 'Failed'] as const).map((option) => <option key={option}>{option}</option>)}
        </select></label>
      </div>
      <div className="table-scroll">
        <table>
          <caption className="sr-only">Payment transactions. Payment APIs are not connected; no transaction data is available.</caption>
          <thead><tr><th scope="col">Transaction</th><th scope="col">Amount</th><th scope="col">Status</th><th scope="col">Date</th><th scope="col">Method</th></tr></thead>
          <tbody><tr><td colSpan={5}>
            <div className="empty-state" role="status">
              <span className="empty-icon"><Icon name={hasFilter ? 'search' : 'receipt'} /></span>
              <h3>{hasFilter ? 'No matching transactions' : 'A fresh start for your payments'}</h3>
              <p>{hasFilter ? 'No transaction data is available to search or filter yet.' : 'Your transactions will appear here once payment APIs are connected.'}</p>
              {hasFilter && <button className="text-button" onClick={() => { setQuery(''); setStatus('All transactions'); searchRef.current?.focus() }}>Clear filters <Icon name="arrow-right" /></button>}
            </div>
          </td></tr></tbody>
        </table>
      </div>
      <div className="panel-footer"><span className="status-dot" />{hasFilter ? 'No results · ' : ''}Waiting for payment data<span className="footer-note">No payments have been loaded</span></div>
    </section>
  )
}

function Overview({ navigate }: { navigate: (page: Page) => void }) {
  const [period, setPeriod] = useState('Last 30 days')

  return (
    <>
      <section className="welcome-banner" aria-labelledby="welcome-title">
        <div className="banner-copy">
          <span className="eyebrow"><span /> BUILT FOR A BETTER PAYMENT JOURNEY</span>
          <h2 id="welcome-title">Your Sandbox checkout,<br />one step closer.</h2>
          <p>Connect your backend, check service health,<br className="desktop-break" /> and prepare your payment flow.</p>
          <button className="button banner-button" onClick={() => navigate('Integrations')}>Finish your setup <Icon name="arrow-right" /></button>
        </div>
        <div className="banner-art" aria-hidden="true">
          <div className="orbit orbit-outer" /><div className="orbit orbit-inner" />
          <span className="orbit-point point-one" /><span className="orbit-point point-two" />
          <div className="shield-tile"><Icon name="shield" /></div>
          <span className="floating-tile tile-top"><Icon name="refresh" /></span>
          <span className="floating-tile tile-bottom"><Icon name="lock" /></span>
          <span className="art-caption">A clearer view of your payment setup.</span>
        </div>
      </section>

      <div className="section-heading"><h2>Your payment snapshot</h2><label className="period-select"><Icon name="calendar" /><span className="sr-only">Snapshot period</span><select aria-label="Snapshot period" value={period} onChange={(event) => setPeriod(event.target.value)}><option>Last 7 days</option><option>Last 30 days</option><option>Last 90 days</option></select></label></div>
      <section className="metrics-grid" aria-label={`Payment metrics, ${period.toLowerCase()}`}>
        {metrics.map((metric) => <article className="metric-card" key={metric.label}>
          <div className="metric-heading"><span>{metric.label}</span><span className={`metric-icon ${metric.color}`}><Icon name={metric.icon} /></span></div>
          <p className="metric-value"><span aria-hidden="true">—</span><span className="sr-only">Unavailable</span><span className="no-data">No data yet</span></p>
          <p className="metric-description">{metric.description}</p>
        </article>)}
      </section>

      <div className="overview-grid">
        <section className="panel activity-panel" aria-labelledby="activity-title">
          <div className="panel-heading"><div><h2 id="activity-title">Payment activity</h2><p>Your payment volume over time.</p></div><span className="chart-legend"><span /> Volume</span></div>
          <div className="chart-placeholder">
            <div className="chart-message"><span className="chart-icon"><Icon name="chart" /></span><h3>The bigger picture, coming soon</h3><p>Connect your APIs to see real payment activity.</p><span className="chart-period">{period} · Data unavailable</span></div>
          </div>
          <div className="activity-footnote"><Icon name="info" /> Charts will use actual payment data once connected.</div>
        </section>
        <section className="panel setup-panel" aria-labelledby="setup-title">
          <div className="panel-heading"><div><span className="mini-eyebrow">LET’S GET STARTED</span><h2 id="setup-title">Make yourself payment-ready</h2></div></div>
          <SetupChecklist />
          <button className="setup-link text-button" onClick={() => navigate('Integrations')}>View integration details <Icon name="arrow-right" /></button>
        </section>
      </div>
      <Transactions compact onViewAll={() => navigate('Transactions')} />
    </>
  )
}

function Integrations({ health, onRecheck }: { health: BackendHealthState; onRecheck: () => void }) {
  return (
    <div className="integration-layout">
      <section className="panel integration-main" aria-labelledby="integration-title">
        <span className="large-icon"><Icon name="plug" /></span>
        <span className="mini-eyebrow">YOUR NEXT STEP</span>
        <h2 id="integration-title">Bring your payments into the picture.</h2>
        <p>The immediate goal is a working PayPal Sandbox payment flow. Payment APIs are currently placeholders, so payment data is unavailable and checkout remains disabled.</p>
        <BackendHealthPanel health={health} onRecheck={onRecheck} />
        <div className="integration-status"><span className="status-dot" /><strong>Payment APIs</strong><span className="badge">Not connected</span></div>
        <SetupChecklist />
        <details className="integration-details"><summary>What needs to happen before checkout?</summary><p>Connect the backend to a payment provider, implement payment creation and status endpoints, and verify payment status on the server. Only enable checkout after the complete flow has been tested.</p><p>This frontend does not initiate payment requests or infer successful payments.</p></details>
      </section>
      <section className="panel checkout-panel" aria-labelledby="checkout-title">
        <span className="checkout-art"><Icon name="lock" /></span>
        <h2 id="checkout-title">Checkout is on hold</h2>
        <p id="checkout-reason">Payment services are not connected. Checkout stays disabled until the backend can create and verify payments.</p>
        <button className="button checkout-button" disabled aria-describedby="checkout-reason"><Icon name="lock" /> Checkout unavailable</button>
        <span className="checkout-note">No payment will be initiated.</span>
      </section>
    </div>
  )
}

function App() {
  const [page, setPage] = useState<Page>('Overview')
  const [menuOpen, setMenuOpen] = useState(false)
  const sidebarRef = useRef<HTMLElement>(null)
  const { health, recheck } = useBackendHealth()
  const healthLabel = health.status === 'checking'
    ? 'Checking backend health'
    : health.status === 'connected' ? 'Backend connected' : 'Backend unavailable'

  useEffect(() => {
    if (!menuOpen) return

    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const mediaQuery = window.matchMedia('(max-width: 760px)')
    sidebarRef.current?.querySelector<HTMLButtonElement>('.sidebar-close')?.focus()

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setMenuOpen(false)
      if (event.key !== 'Tab') return

      const controls = Array.from(sidebarRef.current?.querySelectorAll<HTMLElement>('a[href], button:not([disabled])') ?? [])
        .filter((element) => element.offsetParent !== null)
      const first = controls[0]
      const last = controls[controls.length - 1]
      if (!sidebarRef.current?.contains(document.activeElement)) {
        event.preventDefault()
        const target = event.shiftKey ? last : first
        target?.focus()
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last?.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first?.focus()
      }
    }

    function closeOnDesktop() {
      if (!mediaQuery.matches) setMenuOpen(false)
    }

    document.addEventListener('keydown', handleKeyDown)
    mediaQuery.addEventListener('change', closeOnDesktop)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      mediaQuery.removeEventListener('change', closeOnDesktop)
      if (previousFocus?.getClientRects().length) previousFocus.focus()
      else sidebarRef.current?.querySelector<HTMLButtonElement>('[aria-current="page"]')?.focus()
    }
  }, [menuOpen])

  function navigate(nextPage: Page) {
    setPage(nextPage)
    setMenuOpen(false)
    window.scrollTo(0, 0)
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content" inert={menuOpen}>Skip to content</a>
      {menuOpen && <button className="sidebar-backdrop" tabIndex={-1} aria-label="Close navigation" onClick={() => setMenuOpen(false)} />}
      <aside ref={sidebarRef} id="sidebar" className={`sidebar ${menuOpen ? 'is-open' : ''}`} role={menuOpen ? 'dialog' : undefined} aria-modal={menuOpen || undefined} aria-label="Workspace navigation">
        <button className="sidebar-close" aria-label="Close navigation" onClick={() => setMenuOpen(false)}><Icon name="close" /></button>
        <a className="brand" href="#" onClick={(event) => { event.preventDefault(); navigate('Overview') }} aria-label="RescuePay AI overview"><span className="brand-mark"><Icon name="rescue" /></span><span>RescuePay<span className="brand-ai">AI</span></span></a>
        <div className="workspace-card"><span className="workspace-avatar">R</span><div><strong>RescuePay workspace</strong><span>Development environment</span></div><span className="workspace-indicator" /></div>
        <span className="nav-label">WORKSPACE</span>
        <nav aria-label="Main navigation">
          {navigation.map((item) => <button key={item.page} className={`nav-item ${page === item.page ? 'active' : ''}`} aria-current={page === item.page ? 'page' : undefined} onClick={() => navigate(item.page)}><Icon name={item.icon} /><span>{item.page}</span>{item.page === 'Integrations' && <span className="nav-attention" aria-label="Setup required" />}</button>)}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-tip"><span className="tip-icon"><Icon name="sparkle" /></span><h3>A clear start.<br />A connected payment flow.</h3><p>Connect your backend to prepare your Sandbox checkout.</p><button onClick={() => navigate('Integrations')}>Explore setup <Icon name="arrow-right" /></button></div>
          <button className={`connection-button health-${health.status}`} onClick={() => navigate('Integrations')}><span className="status-dot" /><span>{healthLabel}</span><Icon name="chevron-right" /></button>
          <div className="sidebar-footer"><span className="profile-avatar"><Icon name="code" /></span><div><strong>Developer workspace</strong><span>Frontend preview</span></div><Icon name="shield" /></div>
        </div>
      </aside>

      <div className="workspace-content" inert={menuOpen}>
        <header className="topbar">
          <div className="breadcrumb"><button className="icon-button menu-toggle" aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={menuOpen} aria-controls="sidebar" onClick={() => setMenuOpen(!menuOpen)}><Icon name={menuOpen ? 'close' : 'menu'} /></button><span className="breadcrumb-root">Workspace</span><Icon name="chevron-right" /><span>{page}</span></div>
          <span className="environment-badge"><span /> Development mode</span>
        </header>
        <main id="main-content" tabIndex={-1}>
          <div className="page-heading"><div><span className="mini-eyebrow">YOUR PAYMENT COMMAND CENTER</span><h1>{page}</h1><p>{page === 'Overview' ? 'A little clarity for every payment. Let’s get you set up.' : page === 'Transactions' ? 'Follow every payment, from first attempt to final status.' : 'Connect the services that power your payment flow.'}</p></div><div className="checkout-action"><button className="button" disabled aria-describedby="checkout-hint"><Icon name="plus" /> New payment <Icon name="lock" /></button><span id="checkout-hint">Checkout disabled · APIs not connected</span></div></div>
          <div className="development-notice"><span className="notice-icon"><Icon name="info" /></span><p><strong>You’re in a development workspace.</strong> <span role={page === 'Integrations' ? undefined : 'status'}>{healthLabel}.</span> Payment APIs are not connected. All metrics are unavailable and checkout is disabled.</p><button className="text-button" onClick={() => navigate('Integrations')}>View setup <Icon name="arrow-right" /></button></div>
          {page === 'Overview' ? <Overview navigate={navigate} /> : page === 'Transactions' ? <Transactions /> : <Integrations health={health} onRecheck={recheck} />}
          <footer className="main-footer"><span>Thoughtfully built for payments that move forward.</span><span><Icon name="shield" /> RescuePay AI <span className="footer-divider">/</span> Frontend preview</span></footer>
        </main>
      </div>
    </div>
  )
}

export default App
