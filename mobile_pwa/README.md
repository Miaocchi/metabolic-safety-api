# Mobile PWA

React 19 + Vite 7 mobile PWA for the metabolic safety prototype. Requires Node >=20.19.

```powershell
npm install
npm run dev -- --port 5174
```

Open `http://127.0.0.1:5174/`.

- `/api/*` is served from the repository static export at `public/api`.
- `/local-api/*` is available only as an internal development proxy to `desktop_app/server.py`; it is not part of the mobile user settings.
- The app has a local static database in IndexedDB. Search shards, manifests, and viewed details are cached there.
- The remote database can be configured as a GitHub Pages or Cloudflare Pages static API URL.
- Leaving the Pages URL empty uses the bundled/internal static API endpoint (`/api`) as the authoritative bootstrap/sync source.
- The mobile PMI/safety summary remains visible even when there are no active substances, so users can see profile/status and empty-state guidance instead of losing the panel.
- Journal and profile data are also stored locally in IndexedDB.
- Remote static APIs are for public seed/search/detail JSON only. They must not receive journal/profile data, QR migration payloads, dose history, or local risk inferences.
- QR/text migration contains private profile and journal data and is only for explicit local copy/scan/import flows.
- Remote Pages lookups fetch only public database objects. Live openFDA FAERS fallback may query openFDA with substance names/aliases when static signal data is absent; keep it user-visible/consent-based, optional, and treat results as low-confidence candidate signals.
- Half-life data is exported by the ETL into the static API when available. GitHub Actions builds the same API artifacts for Pages; failures should stop deployment rather than silently publishing stale or partial half-life data.
- Optional local raw-data reference path for development: `D:\metabolic-safety-data` on Windows, mounted as `/mnt/d/metabolic-safety-data` under WSL. This path is not required for normal mobile use.

Verification:

```powershell
npm test
npm run build
npx vitest run src/lib/api.test.ts
npx vitest run src/domain/safety.test.ts src/services/risk-service.test.ts
```
