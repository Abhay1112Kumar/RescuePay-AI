import type { BackendHealthState, HealthUnavailableReason } from '../api/health'
import { Icon } from './Icon'

interface BackendHealthPanelProps {
  health: BackendHealthState
  onRecheck: () => void
}

const failureMessages: Record<HealthUnavailableReason, string> = {
  network: 'Could not reach the health endpoint. The backend may not be running locally, or the API route may need configuration.',
  timeout: 'The health check timed out after 5 seconds. Backend reachability could not be confirmed.',
  http: 'The health request received an unsuccessful response from the service or proxy. Check the local service and API routing.',
  'invalid-response': 'The endpoint did not return the expected health JSON. Check the API route and backend response contract.',
}

const labels: Record<BackendHealthState['status'], string> = {
  checking: 'Checking',
  connected: 'Connected',
  unavailable: 'Unavailable',
}

export function BackendHealthPanel({ health, onRecheck }: BackendHealthPanelProps) {
  return (
    <section className="backend-health-panel" aria-labelledby="backend-health-title">
      <div className="backend-health-heading">
        <h3 id="backend-health-title">Backend health</h3>
        <span className={`badge health-${health.status}`}>
          <span className="status-dot" /> {labels[health.status]}
        </span>
      </div>
      <div className="backend-health-detail" aria-live="polite" aria-atomic="true">
        {health.status === 'checking' && <p>Checking the backend health endpoint…</p>}
        {health.status === 'connected' && (
          <p>Health check passed: <strong>{health.data.service}</strong> · Version {health.data.version}.</p>
        )}
        {health.status === 'unavailable' && (
          <p>{failureMessages[health.reason]}{health.reason === 'http' && health.httpStatus ? ` HTTP ${health.httpStatus}.` : ''}</p>
        )}
      </div>
      <p className="health-scope-note">This checks backend reachability only. It does not verify PayPal connectivity or enable checkout.</p>
      <button className="text-button health-recheck" onClick={onRecheck} disabled={health.status === 'checking'}>
        <Icon name="refresh" /> {health.status === 'checking' ? 'Checking…' : 'Recheck backend health'}
      </button>
    </section>
  )
}
