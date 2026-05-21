# Repository Guidelines

## Project Structure & Module Organization

This monorepo contains a local-first metabolic safety prototype across data, web, desktop, and Android layers. Python ETL code lives in `src/metabolic_safety_etl/`, with tests in `tests/` and utilities in `tools/`. The React/Vite PWA lives in `mobile_pwa/`; source is in `mobile_pwa/src/`, static assets in `mobile_pwa/public/`, and domain tests sit beside modules as `*.test.ts`. The desktop UI is in `desktop_app/`, `site/` is the tracked static viewer, and `android/` is the Capacitor wrapper. Curated inputs live under `data/fixtures/` and `data/overrides/`; generated `build/`, `public/api/`, and `mobile_pwa/dist/` output should not be hand-edited.

## Build, Test, and Development Commands

Run from the repository root unless noted.

- `npm run mobile:install` installs PWA dependencies.
- `npm run mobile:dev` starts Vite on localhost.
- `npm run mobile:test` runs PWA Vitest tests.
- `npm run mobile:build` type-checks and builds the PWA.
- `npm run data:demo` generates demo ETL output under `build/`.
- `npm run data:test` runs the Python test suite through the repo runner.
- `npm run repo:check-generated` verifies generated/cache paths are ignored and untracked.
- `npm run android:sync` syncs Capacitor after `npm run mobile:build`.

## Coding Style & Naming Conventions

Use Python 3.10+ with 4-space indentation, `snake_case` modules/functions, and existing typed structures. Keep adapters traceable: convert upstream data into evidence records before fusion. In TypeScript, use 2-space indentation, `PascalCase` React components, `useX` hook names, and colocated `*.test.ts` files. Keep `mobile_pwa/src/domain/` pure: no React, browser storage, or network side effects.

## Testing Guidelines

Python tests are under `tests/test_*.py`; add focused coverage for changed fusion, dose-rule, static API, or parser behavior. PWA tests use Vitest and live beside domain/lib modules. Run the smallest relevant suite first, then `npm run data:test`, `npm run mobile:test`, `npm run mobile:build`, and `npm run repo:check-generated` before handoff.

## Commit & Pull Request Guidelines

Recent history uses short imperative commit subjects, for example `Fix source layer cache restore fallback`. Keep subjects specific and under about 72 characters. Pull requests should describe the behavior change, list test commands run, link issues or data-source context, and include screenshots for visible PWA, desktop, or static-site UI changes.

## Security & Configuration Tips

Preserve the project rule: unknown is not safe. Do not let candidate, community, or signal sources downgrade higher-tier evidence. Do not send profile, journal, dose history, QR transfer payloads, or locally inferred risks to remote static APIs. The unauthenticated desktop server is localhost-only development tooling.
