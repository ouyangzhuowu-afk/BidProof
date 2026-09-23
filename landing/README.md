# BidProof public page

A static, progressively enhanced product page built with Vite 7, strict TypeScript and Tailwind CSS 4. It shares the existing FastAPI origin and requires no Node process in production. The existing application under `frontend/` is independent.

## Build and verify

Use Node 22.12+ (Node 24 is used for local verification):

```sh
cd landing
npm ci
npm run verify
```

The build writes `static/marketing/index.html`, content-hashed JS/CSS, and public assets. Serve `/` through the FastAPI public-page route and `/static/marketing/*` through the existing static mount. `npm run dev` is an isolated development preview; `/app` and `/privacy` require the backend origin.

All public metadata uses `__PUBLIC_ORIGIN__`, replaced by the backend from the configured public origin. Do not serve the unprocessed index as the production root. This avoids hard-coded third-party canonical URLs. No inline scripts, CDN libraries, remote fonts, or external analytics are required.

## Structure

- `index.html`: readable semantic content, real `/app` CTAs, native FAQ and mobile menu; visible static evidence example without JS.
- `src/demo-model.ts`: typed synthetic cases and fail-closed confirmation eligibility.
- `src/demo.ts`: safe DOM rendering, scoped local notes, keyboard navigation and live status.
- `src/tracking.ts`: optional `bidproof:marketing` CustomEvent hook containing only enumerated `placement` and `action`. It sends no network request; never attach notes, filenames, account IDs or document text.
- `src/main.ts`: isolated demonstration fallback, finite viewport entry animations, reduced-motion and lifecycle cleanup.
- `src/style.css`: Tailwind import, shared marketing tokens and responsive styling.
- `public/social-card.svg`: editable, code-native 1200×630 Open Graph artwork. `social-card.png` is the export used by metadata.
- `tests/demo.test.ts`: domain and DOM tests for rejection guards, confirmation, note isolation/XSS, keyboard flow, reset, listener teardown, telemetry minimization and working links.

The Tailwind Vite setup follows the [official installation guide](https://tailwindcss.com/docs/installation/using-vite). Dependencies are development-only and pinned by `package-lock.json`.

## Content boundaries

All demonstration documents and task counts are visibly labelled synthetic. The demonstration does not call audit APIs, upload files, write workspace records, or retain data in local/session storage. Notes live only in the page and are cleared by reload/reset. Missing evidence and expired-certificate examples cannot be confirmed. A human can confirm the matched example or return it to a doubtful state.

The current product is a pilot. Pricing is not publicly committed, there is no payment checkout, and no customer logos, testimonials, certification badges or measured efficiency claims are invented. The page links to existing authentication, which determines whether personal registration, invitation, trial code or login is available.

The automated suite verifies behavior and static contracts. It does not prove production field Core Web Vitals, commercial conversion rates, OCR accuracy, business acceptance or complete accessibility conformance. Those need field measurement and user evaluation.
