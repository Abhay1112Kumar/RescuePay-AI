# Hackathon source review

Implementation follow-up: [Gemini adapter and Studio runtime results](gemini-implementation.md) supersede the earlier adapter-absence and metadata-only spike status below. No real Gemini call or commercial trial activation has occurred.

Checked 2026-10-31. Source material is reference context, not authority to execute payment tools, disclose credentials, activate trials, publish or submit. No application/dependency change was made during this source review. Existing uncommitted explanation work is preserved.

## Archived PDF inventory

All four user-provided PDFs were rendered and OCR processed (32 pages total); representative substantive pages were also visually inspected. OCR has punctuation/navigation artifacts; no material eligibility/submission/prize section remained wholly unreadable. These are October 3 printouts, not current requirements by themselves.

- paypal1.pdf (12 pages): overview, requirements, prizes, judges and rubric; deadline shown as November 13, 2026 01:30 GMT+5:30. PayPal plus meaningful AI, runnable build, open-source repository and short public video are required.
- paypal2.pdf (5 pages): resources and optional inspiration categories. Autonomous payment agents are examples, not a requirement that overrides RescuePay's read-only AI boundary.
- paypal3.pdf (10 pages): official rules, eligibility, timing, submission/IP requirements and prizes. This is the archived rules snapshot.
- paypal4.pdf (5 pages): October 6 live-build webinar announcement, not a product brief or additional prize condition.

Original source files remain outside the repository; PDFs, OCR intermediates and private account screenshots are not copied into Git.

## Current official requirements

[Rules](https://paypalaihackathon.devpost.com/rules) currently specify submission close November 12, 2026 12:00 Pacific (November 13 01:30 IST), judging December 1-15 (ends December 15 08:00 Pacific), and meaningful Sandbox PayPal plus AI. A runnable build may use complete local setup instead of hosting. Public source/open-source license, English materials or translations, and a public YouTube demo under three minutes are required. Access must work through judging. Five equally weighted criteria cover implementation, design, impact, innovation and presentation. Personal/team eligibility and rights still need entrant verification; this review is not an eligibility certification. Protect credentials; design judge access rather than publishing private keys.

Cash awards: Grand $12k/$8k/$5k, honorable mentions $5k each; AG Grid $5k/$2k/$1k (three third-place winners). A project may receive one Grand plus one Sponsor, or one Honorable Mention plus one Sponsor. Thus $17k is the maximum listed project cash combination, not expected winnings. Render awards are credits. Marketing totals differ on the overview; use the rules table for planning.

## AG Studio feasibility: documentation/metadata only

The [AG Grid sponsor page](https://paypalaihackathon.devpost.com/details/aggrid) emphasizes polished Studio widgets, theming/layout and Studio Agent Framework, beyond a basic grid/chart. Formal rules list use of any AG Grid tools as the sponsor eligibility condition; the sponsor guidance informs competitiveness, not a guaranteed award. Choose tools for a coherent merchant-investigation story, not resource count.

Official [compatibility](https://www.ag-grid.com/studio/react/compatibility/) lists React 17-19+ and TypeScript >=5.8.3 for Studio 3. Current project React 19/TypeScript 6 fits the documented ranges. Executed npm registry metadata query confirms ag-studio-react 3.0.0, React/ReactDOM peer range ^17 || ^18 || ^19 and Commercial license. No installation, typecheck or runtime spike of Studio was performed; compatibility is not yet execution-verified.

[Enterprise terms](https://www.ag-grid.com/studio/react/enterprise-licence/) and [pricing](https://www.ag-grid.com/studio/license-pricing/) describe a commercial subscription with a 45-day evaluation. Built-in grid/chart licensing does not automatically cover standalone Enterprise components in custom widgets. A trial started October 31 reaches December 15; exact expiry/time and judge/repository/redistribution access therefore require explicit confirmation. No trial was requested or activated, and no purchase made.

## Current implementation and recommendation

Verified workspace: feature/payment-explanation at merged-main 8ad3266 in RescuePay-AI-explanation. Existing sanitized projection/interface/panel remain uncommitted. Search of backend, frontend source and docs found no Gemini adapter, google.genai integration or Gemini HTTP target. Therefore the pasted brief's possible adapter completion is not established here. Previous executed foundation checks: 217 backend, 5 evidence, 31 checkout, 14 health tests; lint/build/Ruff passed. No application tests rerun for this documentation-only review; browser panel verification remains pending.

The pasted brief proposes Gemini and an AG Studio investigation dashboard; these are not inferred from the project name. Recommended next slice: implement a bounded Gemini structured-plan adapter behind the existing sanitized interface, with mocked output/error/cancellation tests, then verify the evidence panel using a disposable synthetic database. Require explicit separate authorization before any real Gemini smoke request; do not call PayPal. After that, an isolated Studio widget/filter spike can assess package/build/runtime behavior without rewriting checkout. Confirm licensing through judging before adopting Studio as a required demo dependency.

Outstanding submission gaps: actual model integration/verified AI behavior, browser evidence-panel demonstration, open-source license selection, judge access/setup, English description and public sub-three-minute video. Auth/ownership, verified webhooks and broader payment recovery remain known implementation limits. No winning probability, sponsor qualification, Studio runtime success or completed AI MVP is claimed.
