# BidProof public page

A short, progressively enhanced product page using Vite 7, strict TypeScript and Tailwind CSS 4. It shares the FastAPI origin, requires no Node process in production, and links to the application in `frontend/`.

## Build and verify

Use Node 22.12+ (local verification uses Node 24):

```sh
cd landing
npm ci
npm run verify
```

The build writes `static/marketing/index.html` and content-hashed JS/CSS. Serve `/` through the FastAPI public-page route and `/static/marketing/*` through the static mount. The development server previews the landing; `/app` and `/privacy` require the backend origin.

Metadata uses `__PUBLIC_ORIGIN__`, replaced by the backend from its configured origin. Do not serve the unprocessed index as the production root. The page needs no inline scripts, remote images, CDN libraries, external fonts or analytics SDKs.

## Structure

- `index.html`: one outcome-focused Hero, one main `/app` CTA, a static-first example, three short feature cards, and a privacy link.
- `src/demo-model.ts`: fixed illustrative timeline, with no actual scan-performance claim.
- `src/demo.ts`: safe `textContent` rendering, finite playback, reduced-motion handling, visibility cleanup and accessible busy/status feedback.
- `src/tracking.ts`: optional local `bidproof:marketing` events with enumerated `placement` and `action` only; no network or account/document fields.
- `src/main.ts`: fallback and lifecycle cleanup; page controls survive back/forward-cache restores.
- `src/style.css`: Tailwind import, design tokens and mobile/desktop layouts.
- `tests/demo.test.ts`: static fallback, single-flight timing, reduced motion, page lifecycle, teardown, keyboard semantics and telemetry privacy tests.

Copy comparison, wireframe and component decisions are in `docs/ux-0924/landing-blueprint.md`.

## Content boundaries

All preview inputs and results are synthetic. Playback does not call audit APIs, upload files, write records or use local/session storage. Result rows continue to say missing material or needs review; a matched citation does not become an automatic pass. The displayed 2.4-second playback is an illustration, not an actual processing-time guarantee.

No pricing, customer logos, testimonials, certification badges or measured efficiency claims are invented. Authentication and provider availability are determined by the application and server configuration.

Automated checks verify behavior and static contracts. Field Core Web Vitals, conversion rate, OCR accuracy, commercial acceptance and full accessibility conformance still require separate measurement.
