# BidProof frontend pack

Purpose: compact archive for Claude / code review (no node_modules).

## Layout
- frontend/          Vite source of truth for workbench app logic
  - src/app.js       Main workbench UI logic
  - src/state.js     State helpers
  - src/escape.js    HTML escaping
  - src/i18n.js      Strings
  - vite.config.js   Builds IIFE into ../static/app.js
  - package.json
  - jsconfig.json
- static/            Served HTML/CSS shells (+ landing)
  - index.html, style.css   Workbench shell
  - landing.html/css/js     Marketing landing
  - privacy.html
  - favicon.svg

## Intentionally excluded
- frontend/node_modules
- frontend/package-lock.json
- static/app.js          (Vite build output of frontend/src/app.js — use source instead)
- static/vendor/**       (third-party minified, e.g. lucide)
- static/assets/**       (binary screenshots / images)
- .env / secrets

## Rebuild (optional)
cd frontend
npm install
npm run build
