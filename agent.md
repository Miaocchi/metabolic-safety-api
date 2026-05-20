# agent.md

## Project Shape

This repository is a local-first metabolic safety prototype with four main parts:

- `src/metabolic_safety_etl/` — Python ETL package for source adapters, evidence schemas, conservative fusion, seed export, and static API export.
- `mobile_pwa/` — React 19 + Vite 7 + TypeScript PWA. It has its own `package.json` and lockfile.
- `desktop_app/` — no-third-party Python localhost server and vanilla JS desktop validation UI.
- `android/` — Capacitor Android wrapper around `mobile_pwa/dist`.

The app is not clinical decision support. Preserve the rule: **Unknown is not Safe**.

## Source vs Generated Boundaries

Tracked source/data:

- `src/metabolic_safety_etl/`, `tests/`, `tools/`
- `desktop_app/` and `desktop_app/static/`
- `mobile_pwa/src/`, `mobile_pwa/public/`, `mobile_pwa/package.json`, `mobile_pwa/package-lock.json`
- `android/`
- `site/` — tracked static search/viewer UI copied by CI into generated `public/`
- `data/fixtures/`, `data/overrides/`, and curated portions of `data/raw/`
- `docs/`, `.github/workflows/`, `pyproject.toml`, `package.json`, `capacitor.config.json`

Generated or cache output; do not hand-edit or commit unless explicitly requested:

- `build/`, `build_ddinter/`
- `public/` and `public/api/`
- `mobile_pwa/dist/`, `node_modules/`, `mobile_pwa/node_modules/`
- `__pycache__/`, `*.pyc`, `.pytest_cache/`, `*.tsbuildinfo`
- `*.sqlite`, `*.sqlite-shm`, `*.sqlite-wal`, `*.log`, `*.pid`
- large raw downloads under `data/raw/openfda_label/`, `data/raw/dailymed_spl/`, `data/raw/chembl/`, `data/raw/foodrugs/`, `data/raw/onsides/`, `data/raw/pharmgkb/`

## Commands

Run from repo root unless a command says otherwise.

### Root npm delegates

```bash
npm run mobile:dev
npm run mobile:build
npm run mobile:test
npm run mobile:preview
npm run data:demo
npm run data:test
npm run data:export-static-api
npm run data:sources
npm run android:sync
npm run android:open
```

The `data:*` scripts use `tools/npm_python_runner.js` to try `python3`/`python` on POSIX and `py -3`/`python`/`python3` on Windows, then inject `src` into Python's import path so they work without an editable install.

### Python ETL

```bash
PYTHONPATH=src python -m metabolic_safety_etl.cli demo --out build
PYTHONPATH=src python -m metabolic_safety_etl.cli import-ddinter --input-dir data/raw/ddinter --out build
PYTHONPATH=src python -m metabolic_safety_etl.cli export-static-api --input-dir build --out public/api
PYTHONPATH=src python -m metabolic_safety_etl.cli build-public-api --out build --api-out public/api --max-public-terms 20 --public-limit 1 --psychonautwiki-pages 1
PYTHONPATH=src python -m unittest discover -s tests
```

`pyproject.toml` exposes `metabolic-etl = metabolic_safety_etl.cli:main` when the package is installed editable.

### PWA

Vite 7 requires Node >= 20.19.

```bash
cd mobile_pwa
npm install
npm run dev -- --port 5174
npm test
npm run build
```

### Desktop

```bash
PYTHONPATH=src python -m metabolic_safety_etl.cli demo --out build
python desktop_app/server.py
# open http://127.0.0.1:8765
```

Do not expose the desktop server publicly; it is localhost development tooling with no authentication.

### Android

Build PWA assets before Capacitor sync/open:

```bash
npm run mobile:build
npm run android:sync
npm run android:open
```

## Architecture Rules

### Python ETL

- `cli.py` is the stable entrypoint for `python -m metabolic_safety_etl.cli` and `metabolic-etl`.
- Command implementations live under `src/metabolic_safety_etl/cli_modules/`:
  - `commands_build.py` — `demo`, `build`, `import-ddinter`, `inspect`
  - `commands_fetch.py` — source-specific fetch commands
  - `commands_api.py` — `export-static-api`, `build-public-api`
  - `commands_sources.py` — source catalog, remote manifests, raw source mirror commands
  - `helpers.py` — shared CLI helper utilities
- Keep adapters converting upstream data into traceable `EvidenceFact` records before fusion.
- Conservative fusion must preserve the highest known risk and must not let candidate/community/signal sources downgrade higher-tier evidence.

### Mobile PWA

- `src/domain/` owns pure logic and must stay free of React/browser storage/network side effects.
- Canonical pure modules are now:
  - `src/domain/format.ts`
  - `src/domain/pk.ts`
  - `src/domain/risk-computation.ts`
  - existing `src/domain/safety.ts` and `src/domain/risk.ts`
- `src/lib/format.ts`, `src/lib/pk.ts`, and `src/lib/risks.ts` are deprecated re-export bridges. New imports should use `src/domain/*` directly.
- `src/lib/api.ts` and `src/lib/db.ts` remain low-level IO bridges until consumers move fully behind `src/repositories/` and `src/services/`.
- Remote static APIs must not receive profile, journal, dose history, QR transfer payloads, or locally inferred risks.

### Static UI Directories

- `site/` is tracked source for the lightweight GitHub Pages/Cloudflare Pages UI.
- `public/` is generated deployment output. CI builds `public/api/` and copies `site/` into `public/`.
- `desktop_app/static/` is a separate tracked desktop validation UI served by `desktop_app/server.py`.
- `mobile_pwa/public/` is PWA static asset source copied into `mobile_pwa/dist/` by Vite.

## Validation Checklist For Agents

Use the smallest relevant checks first, then broader checks before handing off:

```bash
PYTHONPATH=src python -m unittest discover -s tests
npm run mobile:test
npm run mobile:build
```

For structure refactors, also check:

```bash
git check-ignore -v build/ public/ node_modules/ mobile_pwa/dist/ '*.pyc' '*.part' '*.sqlite'
git ls-files -- '*/__pycache__/' '*.pyc' node_modules/ mobile_pwa/dist/ build/ public/
```

If Android packaging changed, run `npm run mobile:build && npm run android:sync` on a machine with Android/Capacitor tooling available.
