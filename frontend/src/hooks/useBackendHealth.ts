import { useCallback, useEffect, useRef, useState } from 'react'
import { checkBackendHealth, type BackendHealthState } from '../api/health'

export function useBackendHealth() {
  const [health, setHealth] = useState<BackendHealthState>({ status: 'checking' })
  const [attempt, setAttempt] = useState(0)
  const inFlight = useRef(true)

  useEffect(() => {
    const controller = new AbortController()
    inFlight.current = true

    void checkBackendHealth({ signal: controller.signal })
      .then((result) => {
        if (!controller.signal.aborted) setHealth(result)
      })
      .catch(() => {
        if (!controller.signal.aborted) setHealth({ status: 'unavailable', reason: 'network' })
      })
      .finally(() => {
        if (!controller.signal.aborted) inFlight.current = false
      })

    return () => controller.abort()
  }, [attempt])

  const recheck = useCallback(() => {
    if (inFlight.current) return
    inFlight.current = true
    setHealth({ status: 'checking' })
    setAttempt((previous) => previous + 1)
  }, [])

  return { health, recheck }
}
