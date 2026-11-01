# APIMatic + Bryntum sponsor evaluation

## APIMatic PayPal Context Plugin

The official APIMatic marketplace lists the PayPal Context Plugin v0.4.1,
MIT-licensed, for Codex/VS Code and other coding assistants. It was installed
into the local VS Code context-plugin directory for development-time review
only. No PayPal credentials, payment records, or provider calls were sent to
the plugin.

The plugin provided generated SDK contract guidance for OAuth client
credentials, the canonical Sandbox base URL, Orders/Captures controllers,
idempotency, typed errors, transport timeouts, and the distinction between
transport uncertainty and known failures. This review confirmed that the
existing RescuePay HTTP integration already enforces the canonical Sandbox
target, explicit identity/money checks, bounded timeouts, idempotency and
uncertain-outcome handling. No generated SDK was introduced because changing
the transport would add compatibility risk without a demonstrated benefit.

APIMatic usage evidence is the installed local plugin and this comparison;
there was no PayPal API request and no generated-code change.

## Bryntum timeline spike

`spikes/bryntum` contains a separate React/Bryntum Scheduler implementation
using only synthetic/demo records. It projects owner-eligible records into a
read-only timeline with payment reference, backend state, evidence freshness,
reconciliation deadline, uncertain/stale markers, safe backend-approved next
action, and ordered audit events. Unsupported states/actions fall back to
safe display values. No buyer PII, credentials, raw provider payloads or
unnecessary provider identifiers are accepted.

The spike is explicitly disabled unless
`VITE_BRYNTUM_TIMELINE_ENABLED=true`. Disabled, loading, empty,
unavailable/error, and narrow-screen states are implemented. The normal
RescuePay application does not import this package.

The UI is labelled `SYNTHETIC/DEMO EVIDENCE ONLY` and uses a narrow-screen CSS
layout. Bryntum receives no action callbacks capable of capture, refund,
amount changes, PayPal refresh, or payment-success decisions. Gemini is not
connected; a future grounded fact/action selection would appear as a separate
read-only annotation, while backend evidence remains authoritative.

## Version and licence status

- `@bryntum/scheduler-trial`: 7.3.7 (alias target)
- `@bryntum/scheduler-react`: 7.3.7
- React: 19.3.1
- TypeScript: 6.0.3
- Vite: 8.3.5

The trial package was not installed or activated. Bryntum documents a
14-day unlicensed evaluation, a 45-day key-based trial, watermark/console
notices, and commercial Business/Enterprise licensing. Trial/judge access,
public repository rights, and use through the judging period are unconfirmed.
This spike must not become a hidden runtime dependency. No sponsor-prize
eligibility is claimed.

## Judge setup impact and limitations

The main RescuePay application does not require Bryntum. A judge can run the
existing React/FastAPI checkout and sanitized evidence panel without this
spike. If Bryntum rights are later confirmed, the spike requires its own
dependency install and licence arrangement; otherwise use the existing React
timeline/evidence panel as the no-commercial-dependency fallback.

The isolated model tests pass without installing Bryntum (4 tests). A full
Bryntum typecheck/build/browser run is intentionally pending licence/access
approval; the feature flag defaults to disabled so normal application startup
does not require the commercial package.
