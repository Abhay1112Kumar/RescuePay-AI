# Isolated AG Studio investigation spike

Synthetic-only evaluation, deliberately separate from the application and its dependencies. No PayPal data, real AI, agent tools or payment actions.

From this directory: npm ci --ignore-scripts; npm run check; npm run build; npm run dev. Open http://127.0.0.1:5177/.

AG Studio React 3.0.0 / React 19.3.1: installation, strict TypeScript check and Vite build executed successfully. Real browser rendered the custom Payment investigation widget; Show uncertain payments filtered three scenarios to one CAPTURE_UNCERTAIN record, and Show all scenarios restores them. Studio datasource and widget form are configured. Initial missing-form runtime error and custom-registry type errors were resolved before final checks.

No license key or commercial trial was activated. Library emits expected missing-license/evaluation messages. This is a commercial package, not an open-source component license grant; do not deploy or assume judge access. Confirm evaluation/redistribution/judging permissions with vendor before making this a required product dependency. A build warning reports a roughly 5.49 MB JS chunk (1.54 MB gzip); no main application bundle impact because this is isolated. No Studio agent/model framework was enabled; that is a separate feasibility task.

See ../../docs/gemini-implementation.md for full milestone boundaries. node_modules/dist are ignored; lockfile records the separate spike dependency tree.
