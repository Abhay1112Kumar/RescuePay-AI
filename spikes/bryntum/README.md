# Bryntum Payment Recovery Timeline (isolated spike)

This spike renders sanitized synthetic/demo payment evidence as a read-only
recovery timeline. It is deliberately separate from the RescuePay frontend and
does not import the backend, PayPal client, Gemini adapter, or credentials.

## Dependency/licence boundary

The manifest pins Bryntum Scheduler 7.3.7 and its React wrapper, using the
public `@bryntum/scheduler-trial` alias. The trial package is **not installed
or activated in this milestone**. Bryntum documents a 14-day unlicensed trial,
an optional 45-day trial key, watermark/console notices, and commercial terms
for Business/Enterprise tiers. A valid licence or written hackathon grant is
required before this becomes a judge-facing dependency. The Community tier
must be evaluated separately if its feature set is sufficient.

## Planned local verification

After licence approval only: set `VITE_BRYNTUM_TIMELINE_ENABLED=true`, then
run `npm ci`, `npm test`, `npm run check`, `npm run build`, `npm run dev` and
open `http://127.0.0.1:5179/`. With the flag absent/false the spike renders an
accessible disabled state and the normal RescuePay application remains
dependency-free. No PayPal/Gemini calls are needed. Current model tests run
without Bryntum installed and validate ownership filtering, redaction,
ordering, uncertain/stale display, safe-action fallback, and feature disable.
