import { useEffect, useState, useSyncExternalStore } from 'react'
import { createCheckoutApi } from '../api/checkout'
import { CheckoutController } from '../checkout/controller'

export function useSandboxCheckout() {
  const [controller] = useState(() => new CheckoutController({
    api: createCheckoutApi(),
    // Access may throw in restricted browser sessions; the controller fails closed.
    storage: {
      getItem: (key) => window.sessionStorage.getItem(key),
      setItem: (key, value) => window.sessionStorage.setItem(key, value),
      removeItem: (key) => window.sessionStorage.removeItem(key),
    },
    location: () => window.location,
    redirect: (url) => window.location.assign(url),
    clearCallback: () => window.history.replaceState(null, '', '/checkout'),
    uuid: () => window.crypto.randomUUID(),
  }))
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot)
  useEffect(() => {
    void controller.start()
    return controller.stop
  }, [controller])
  return { controller, state }
}
