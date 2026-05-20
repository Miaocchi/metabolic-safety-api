# Architecture

This repository is a local-first safety and evidence-fusion prototype. The computer-side ETL builds traceable seed data; the desktop server validates data and workflows; the mobile PWA consumes a static API and local IndexedDB cache for user logging, risk review, curve display, and evidence traceability.

The app is not a clinical decision support system. It must not present missing evidence as safety.

## Repository map

```text
src/metabolic_safety_etl/   Python ETL, source adapters, schema, fusion, static API export
desktop_app/                Local no-dependency HTTP server and browser test UI
mobile_pwa/                 React 19 + Vite 7 + TypeScript mobile/PWA client
mobile_pwa/src/pages/       Search, Journal, Risks, Curve, Settings pages
mobile_pwa/src/services/    PWA application use cases
mobile_pwa/src/repositories/ IndexedDB/static API persistence interfaces
mobile_pwa/src/domain/      Pure safety/risk rules and tests
android/                    Capacitor Android wrapper for mobile_pwa/dist
docs/                       Static API, Pages deployment, and architecture docs
data/                       Raw and optional source inputs/caches
build/                      Generated local seed JSON/SQLite outputs
public/api/                 Generated static JSON API for remote/bundled client use
```

### Authoritative directory table

| Directory / File | Source or Generated | Committed | Purpose |
| --- | --- | --- | --- |
| `src/metabolic_safety_etl/` | Source | Yes | Python ETL package: adapters, schema, fusion, CLI, static API export |
| `tests/` | Source | Yes | Python unit tests for ETL, fusion, static API |
| `desktop_app/` | Source | Yes | Stdlib localhost HTTP server (`server.py`) and full desktop frontend (`static/`); reads `build/` for seed data |
| `desktop_app/static/` | Source | Yes | Vanilla JS desktop frontend (journal, risk panels, substance search, PK curves); served by `server.py` on localhost:8765 |
| `mobile_pwa/` | Source | Yes | React 19 + Vite 7 + TypeScript PWA client; has its own `package.json` and lockfile |
| `mobile_pwa/dist/` | Generated | No (gitignored) | PWA build output consumed by Capacitor `webDir` |
| `mobile_pwa/public/` | Source | Yes | PWA static assets (icon, manifest, service worker); copied into `dist/` during build |
| `mobile_pwa/node_modules/` | Generated | No (gitignored) | npm dependencies for PWA |
| `android/` | Source | Yes | Capacitor Android wrapper; Gradle project wrapping `mobile_pwa/dist` |
| `android/app/src/main/java/com/metabolicsafety/app/` | Source | Yes | Android `MainActivity` (Capacitor bridge entry) |
| `android/app/src/test/` | Source | Yes | Local JVM unit tests for Android wrapper |
| `android/app/src/androidTest/` | Source | Yes | Instrumented tests for Android wrapper |
| `docs/` | Source | Yes | Architecture, deployment, and data source documentation |
| `data/raw/` | External input | Partially (`.gitignore` excludes large downloads) | Raw upstream source data: DDInter CSV, openFDA, DailyMed, ChEMBL, etc. |
| `data/optional/` | Generated/cache | Partially | Optional public-source fact caches (`public_facts.json`) |
| `build/` | Generated | No (gitignored) | Local ETL outputs: `init_substances.json`, `init_interactions.json`, `evidence_facts.json`, `manifest.json`, `app_seed.sqlite` |
| `build_ddinter/` | Generated | No (gitignored) | Intermediate DDInter import artifacts |
| `public/api/` | Generated | No (gitignored; CI rebuilds) | Static JSON API shards for GitHub Pages / Cloudflare Pages |
| `site/` | Source | Yes | Vanilla JS search/viewer UI for GitHub Pages / Cloudflare Pages; CI copies into `public/` root during deploy |
| `tools/` | Source | Yes | Auxiliary scripts and tooling |
| `pyproject.toml` | Source | Yes | Python project metadata; exposes `metabolic-etl` CLI entrypoint |
| `capacitor.config.json` | Source | Yes | Capacitor config; `appId=com.metabolicsafety.app`, `webDir=mobile_pwa/dist` |
| `package.json` | Source | Yes | Monorepo root scripts and Capacitor CLI dependencies |
| `package-lock.json` | Generated | Yes | Root npm lockfile for Capacitor dependencies |
| `node_modules/` | Generated | No (gitignored) | Root-level npm dependencies |
| `agent.md` | Source | Yes | Agent instructions, repo map, command reference, safety rules |
| `README.md` | Source | Yes | Project overview, quickstart, and feature documentation |
| `.github/workflows/` | Source | Yes | CI: data API build, Cloudflare Pages deploy, UI hotfix deploy |
| `.gitignore` | Source | Yes | Git ignore rules for generated outputs and large data |

Generated outputs (`build/`, `public/api/`, `mobile_pwa/dist/`) are products of ETL commands or CI builds and should not be hand-edited except for an explicit artifact hotfix. `site/` and `desktop_app/static/` are tracked source code — vanilla JS apps for different deployment targets.

## Data and evidence architecture

All source adapters should convert upstream data into `EvidenceFact`-style records before fusion. This prevents app code from depending on source-specific formats and makes every user-facing rule traceable.

```text
source adapters -> raw facts -> normalized EvidenceFact -> fusion -> seed JSON + app_seed.sqlite -> static API/PWA cache
```

Source tiers and default policies:

| Layer | Examples | Purpose | Default policy |
| --- | --- | --- | --- |
| Regulatory/label | DailyMed SPL, openFDA labels, FDA tables | Warnings, contraindications, PK/PD label text | Can be evidence; natural language still needs extraction/review before it becomes a rule |
| Ontology/mapping | RxNorm/RxNav, UNII, ATC, ChEMBL IDs | Entity normalization and aliases | Mapping only; does not create safety claims |
| Curated knowledge | DDInter, PharmGKB/ClinPGx, ChEMBL, licensed DrugBank | DDI/DFI/PK/PGx facts | Candidate/core facts after source-specific mapping and review policy |
| Signal discovery | FAERS/openFDA events, OnSIDES/TwoSIDES, FooDrugs, literature mining | Long-tail signal detection | Candidate signal only; not proof of causality or incidence |
| Community coverage-gap | PsychonautWiki, similar community data | Missing substance names, routes, duration, dose candidates | Candidate/coverage-gap only; cannot downgrade higher-tier risk |

Important fields in an evidence record include `fact_type`, `subject_ids`, `claim`, `risk_level`, `confidence`, `source_tier`, `source_name`, `source_url`, `evidence_quote`, `extraction_method`, `review_status`, and `use_policy`.

## Safety, privacy, and traceability model

- **Unknown is not Safe.** `Unknown` means insufficient evidence. Only `NoKnownClinicalSignificance` means no known clinical significance, and even that should normally be quiet rather than displayed as a positive safety guarantee.
- **Conservative fusion.** For the same pair/claim, preserve the highest known risk. Lower-tier signal or community data must not reduce a regulatory, guideline, curated, or human-reviewed risk.
- **Community and pharmacovigilance signals are candidates.** FAERS/openFDA event counts, PsychonautWiki, FooDrugs, OnSIDES/TwoSIDES, and LLM extraction output may surface blind spots, but they should be marked `candidate_signal` until reviewed and supported by traceable evidence.
- **Evidence traceability is mandatory.** User-facing risks need evidence refs/quotes/source URLs where possible. Raw label text (`source_text`) alone is evidence material, not automatically an actionable rule.
- **Historical interpretation is snapshot-based.** Journal entries should keep the relevant profile/substance parameter snapshot. Updating the seed database must not silently rewrite the meaning of past logs.
- **Remote fallback privacy.** The PWA should prefer local/static data. A configured remote static API is for seed/search/bundle lookup, not user journal upload. Remote lookups may reveal searched substance names or IDs to the remote host; therefore remote endpoints should be user-configurable and empty/offline/local-first modes must remain valid. Do not send personal profile, journal entries, dose history, or locally inferred risks to the static remote API.
- **QR transfer privacy.** QR/text migration payloads contain private profile and journal data. They are local export/import payloads for explicit copy/scan workflows and must not be uploaded to the remote static API.
- **Live signal consent.** The live openFDA FAERS fallback can send substance names/aliases to openFDA when static signal data is absent. Keep this path user-visible/consent-based, and label the result as low-confidence pharmacovigilance signal rather than confirmed causality or incidence.

## Mobile PWA architecture

Current implementation uses dedicated pages, repositories, services, domain helpers, compatibility `lib` bridges, and `App.tsx` as the top-level shell. Keep new work within these boundaries without large opportunistic rewrites.

| Layer | Current location | Target responsibility |
| --- | --- | --- |
| `app` | `src/main.tsx`, `src/App.tsx` | App bootstrap, providers, top-level shell, tab orchestration, dependency wiring |
| `pages` | `src/pages/` | Route/tab-level screens such as Search, Journal, Risks, Curve, Settings |
| `components` | `src/components/` | Reusable visual building blocks; no direct API/IndexedDB writes except via props/callbacks |
| `hooks` | `src/hooks/usePlatform.ts` | UI/device state, media queries, haptics, and later page-specific view hooks |
| `repositories` | `src/repositories/` plus low-level `src/lib/api.ts`/`src/lib/db.ts` | Persistence and data access interfaces: static API, desktop local API, IndexedDB cache/journal/settings |
| `services` | `src/services/` | Application use cases: sync static DB, hydrate cache, remote fallback, import transfer, risk evaluation |
| `domain` | `src/domain/`, `src/types.ts` | Shared domain types, safety/risk rules, risk computation, PK modeling, formatting/search helpers, route/stomach/profile vocabulary, invariants |
| `viewmodels` | `App.tsx` and page-local state/effects | Screen state derivation and commands; bridge pages to services/repositories |
| `data` | `src/lib/db.ts`, static JSON payloads, IndexedDB stores | Local data schemas, DTOs, cache records, generated static API payload contracts |

Recommended boundaries:

- `domain` and pure risk/PK/format logic (`domain/risk-computation.ts`, `domain/pk.ts`, `domain/format.ts`) should remain testable without React or browser storage.
- `repositories` should own IO details (`fetch`, IndexedDB object stores, local desktop API paths). UI code should not construct all URLs or IndexedDB transactions directly.
- `services` should combine repositories into workflows such as “search remote then cache bundle” or “load local seed into cache”.
- `viewmodels` should prepare localized labels and command handlers for `pages`; reusable `components` should stay presentation-oriented.
- Remote static API fallback must not receive journal/profile data.
- `src/lib/format.ts`, `src/lib/pk.ts`, and `src/lib/risks.ts` are deprecated re-export bridges for legacy imports; new code should import from `src/domain/*`. `src/lib/api.ts` and `src/lib/db.ts` remain low-level IO until their consumers fully move behind repositories/services.

## Desktop server architecture

### Current implementation

The desktop test app remains a no-third-party Python localhost server, but it is no longer a pure monolith. `desktop_app/server.py` owns the HTTP entrypoint, static files, and request dispatch; shared config and service logic live in `desktop_app/config.py` and `desktop_app/services/`:

- **Routes:** `Handler.do_GET` dispatches `/api/seed`, `/api/interactions`, `/api/check`, `/api/adverse-signals`, `/api/sources`, `/api/source-update`, `/api/rebuild`, `/api/public-sync`, `/api/bulk-sync`, `/api/rebuild-status`, `/api/label-bulk-manifest`, `/remote-api/*`, and `/health`.
- **Services:** `desktop_app/services/source_ops.py` manages public source fetch/sync/rebuild operations; `job_manager.py` owns background job state; server methods still perform seed reads, interaction checks, and response mapping.
- **Security:** `desktop_app/services/security.py` contains input/path/URL helpers. The server is intended for localhost development, uses stdlib HTTP serving, has no authentication, and should not be exposed on a public network. It reads/writes generated local data and optional caches only.
- **Models:** persisted seed models live in generated JSON/SQLite from the ETL (`substances_core`, `interactions_core`, evidence rows, dose rules, manifests). Runtime payload shapes mirror mobile `types.ts` and ETL schemas.

### Incremental migration plan

Continue splitting route groups only when changing that area, while preserving the current no-dependency/local-first constraint unless the project intentionally adopts a framework:

```text
desktop_app/
  server.py              bootstrap, HTTP server, static files, wiring
  config.py              path constants, source configs, sys.path setup
  routes/                future request parsing and response mapping per route group
  services/              source sync, rebuild jobs, job state, security helpers, future seed/check services
  models/                request/response DTOs and SQLite row mappers
```

Migration order should be route-addition friendly: extract a route group only when changing that area, keep behavior covered by smoke tests, and avoid broad rewrites that conflict with feature agents.

## ETL/package architecture

- `schemas.py` defines portable evidence and seed data shapes.
- `adapters/` converts individual sources (DDInter, DailyMed, openFDA, RxNav, ChEMBL, PsychonautWiki, label bulk data) into facts or mapping records.
- `fusion.py` applies conservative evidence/risk merge rules and produces core seed structures.
- `export.py` writes local JSON/SQLite outputs under `build/`.
- `static_api.py` shards and exports the static JSON API under `public/api/`.
- `cli.py` is the stable command entrypoint; command implementations are split by responsibility under `cli_modules/` (`commands_build.py`, `commands_fetch.py`, `commands_api.py`, `commands_sources.py`, `helpers.py`). `pyproject.toml` also exposes `metabolic-etl` when installed editable.

## Development commands

Run Python commands from repo root. On Windows PowerShell use `$env:PYTHONPATH="src"`; on POSIX shells use `PYTHONPATH=src` before the command.

Root `package.json` also provides delegating scripts for common workflows:

```powershell
npm run mobile:dev
npm run mobile:build
npm run mobile:test
npm run data:demo
npm run data:test
npm run data:export-static-api
npm run android:sync
npm run android:open
```

The root `data:*` npm scripts use `tools/npm_python_runner.js` to try `python3`/`python` on POSIX and `py -3`/`python`/`python3` on Windows, then inject `src` into Python's import path. You can still use the explicit Python commands below or install the package editable.

### Data build and ETL

```powershell
$env:PYTHONPATH="src"
python -m metabolic_safety_etl.cli demo --out build
python -m metabolic_safety_etl.cli import-ddinter --input-dir data/raw/ddinter --out build
python -m metabolic_safety_etl.cli export-static-api --input-dir build --out public/api
python -m metabolic_safety_etl.cli build-public-api --out build --api-out public/api --max-public-terms 20 --public-limit 1 --psychonautwiki-pages 1
python -m metabolic_safety_etl.cli sources --out build/source_status.json
```

If the package is installed editable, `metabolic-etl ...` can be used instead of `python -m metabolic_safety_etl.cli ...`.

### Desktop server

```powershell
$env:PYTHONPATH="src"
python -m metabolic_safety_etl.cli demo --out build
python desktop_app/server.py
# or
python -m desktop_app.server
```

Open `http://127.0.0.1:8765`. Stop a background server with the PID written in `build/desktop_server.pid` if present:

```powershell
Stop-Process -Id (Get-Content build/desktop_server.pid)
```

### Mobile PWA

Requires Node >=20.19 for Vite 7.

```powershell
cd mobile_pwa
npm install
npm run dev -- --port 5174
npm test
npm run build
npm run preview
```

Focused tests can be run with Vitest, for example:

```powershell
cd mobile_pwa
npx vitest run src/lib/api.test.ts
npx vitest run src/domain/safety.test.ts src/services/risk-service.test.ts
```

### Android wrapper

Build PWA assets before using the Capacitor wrapper:

```powershell
cd mobile_pwa
npm run build
cd ..\android
# run the appropriate Gradle/Android Studio build task from this directory
```

`capacitor.config.json` points `webDir` at `mobile_pwa/dist`.

### Tests

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests
python -m unittest tests.test_static_api

cd mobile_pwa
npm test
npx vitest run src/lib/risks.test.ts
```

## Deployment/static API docs

- GitHub Pages static API: `docs/REMOTE_STATIC_API.md`
- Cloudflare Pages static API: `docs/CLOUDFLARE_PAGES_API.md`
- Data/source project scheme notes: `docs/PROJECT_SCHEME.md`
