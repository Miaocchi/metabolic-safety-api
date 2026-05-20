# Cloudflare Pages Remote Static API

This deployment target is the lowest-cost option for the remote fallback: no Workers, no D1, no KV, and no R2. It deploys only static JSON files under `public/api`.

## Cost Boundary

Use the Cloudflare Pages Free plan and static assets only. Do not add Pages Functions, Workers, D1, KV, R2, Vectorize, or Workers AI unless you intentionally accept those products' quotas and possible charges.

Current official Pages limits to watch:

- Free plan build limit: 1 concurrent build and 500 builds per month.
- Free plan file limit: 20,000 files per site.
- Single static asset size limit: 25 MiB.

The exported API is sharded by hashed paths so Windows/GitHub/Cloudflare path length limits are avoided. If a future full dataset exceeds 20,000 files or a bucket exceeds 25 MiB, the exporter must switch to larger shards or an external object store. Do not use R2 if the requirement is zero additional cost risk.

## GitHub Secrets and Variables

Create these GitHub repository secrets:

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`

The token only needs Cloudflare Pages edit access for the account.

Optional repository variable:

- `CLOUDFLARE_PAGES_PROJECT`, default `metabolic-safety-api`

## Deployment Workflow

The workflow is `.github/workflows/build-data-api-cloudflare-pages.yml`.

It runs tests, builds the fused seed database, exports `public/api`, exports seed-backed overlays via `tools/export_dose_overlay.py`, writes `_headers` for CORS, creates the Pages project if needed, and deploys with:

```text
wrangler pages project create <project> --production-branch=main
wrangler pages deploy public --project-name=<project> --branch=main
```

### Overlay Step

After `build-public-api` produces `build/app_seed.sqlite`, the workflow runs:

```text
python tools/export_dose_overlay.py \
  --api-dir public/api \
  --max-content-per-substance "${MAX_CONTENT_PER_SUBSTANCE}" \
  --structured-db build/app_seed.sqlite
```

This writes the overlay endpoint structure supported by the exporter (drug-effects, pharmacokinetics, enzyme-relations, label-sections, safety-warnings, interaction-signals, food-interactions, adverse-signals, pgx, dose-candidates, overdose-warnings, dose-rules) and rewrites search shards into `public/api/`.

The `max_content_per_substance` input (default 24, matching the main Pages workflow) caps per-substance rows for content overlays; set to 0 to export all.

> **Coverage note**: The Cloudflare workflow intentionally uses `--structured-db build/app_seed.sqlite` instead of `--fact-json` per-source caches because it does **not** run the heavy source-layer-cache matrix. Therefore the endpoint paths/manifests are present, but data coverage is limited to facts loaded into the seed build (`data/optional`, `data/overrides`, and the bounded public API build). The full label/safety/FooDrugs/OnSIDES/PharmGKB coverage is produced by the main GitHub Pages workflow (`build-data-api.yml`), which streams six source-layer JSON caches.

This keeps Cloudflare Pages at the static-only/lowest-cost boundary. Do not add Pages Functions, Workers, D1, KV, R2, Vectorize, or Workers AI just to fill the coverage gap unless you explicitly accept those product limits and cost risks.

After deployment, configure the local app remote source as:

```text
https://<project>.pages.dev/api
```

or your custom Cloudflare Pages domain ending at `/api`.
