# Remote Static Drug API via GitHub Pages

Goal: keep the desktop/mobile client lightweight. The local app keeps the core seed database, and only when a local lookup misses can the user enable a GitHub Pages hosted static JSON API as a remote fallback.

## Build Flow

1. GitHub Actions runs `Build Static Drug API` on push, schedule, or manual dispatch.
2. The workflow builds the fused seed database. It prefers repository `data/raw/ddinter/*.csv`; if those files are absent it falls back to the bundled fixture dataset so the pipeline remains testable.
3. `python -m metabolic_safety_etl.cli export-static-api --input-dir build --out public/api` converts the fused seed JSON into static JSON files that GitHub Pages can host.
4. `actions/deploy-pages` publishes `public/` to GitHub Pages.

## Static API Paths

GitHub Pages does not run a dynamic backend. The API is therefore a static file API:

- `api/manifest.json`: API version, dataset version, counts, and path templates.
- `api/search/index.json`: compact search index. The client downloads it and filters locally.
- `api/substances/by-id/{id}.json`: one substance detail record.
- `api/interactions/by-substance/{id}.json`: DDI/DFI rows involving one substance.
- `api/dose-rules/by-substance/{id}.json`: dose threshold rules involving one substance.

Configure the local app with the `/api` base URL, for example:

```text
https://<your-name>.github.io/<repo>/api
```

## Privacy Boundary

Remote fallback is off by default. When enabled, the browser requests remote static files only after a local miss or when a cached remote substance is used. The remote host can see file requests for the search index and substance IDs. Keep the option disabled if no query should leave the device.

## Large Label Sources

openFDA and DailyMed bulk label archives are too large to keep on the client. They should be processed by a workstation or GitHub Actions into structured, lightweight `substances`, `interactions`, `dose_rules`, and evidence summaries before publication.
