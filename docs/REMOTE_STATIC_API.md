# Remote Static Drug API via GitHub Pages

Goal: keep the desktop/mobile client lightweight. The local app keeps the core seed database, and only when a local lookup misses can the user enable a GitHub Pages hosted static JSON API as a remote fallback.

## Build Flow

1. GitHub Actions runs `Build Static Drug API` on push, schedule, or manual dispatch.
2. The workflow runs `build-public-api`, which starts from DDInter/local override facts, then enriches selected substance terms through every directly usable open API adapter: RxNav, ChEMBL, DailyMed, openFDA label, and PsychonautWiki.
3. Optional normalized fact files under `data/optional` and `data/overrides` are merged in the same pass, so local exports from FooDrugs, OnSIDES, PharmGKB/ClinPGx, or other open datasets can be added without changing the mobile client.
4. `build-public-api` writes both mobile seed files and the GitHub Pages static JSON API under `public/api`.
5. `actions/deploy-pages` publishes `public/` to GitHub Pages.

## Static API Paths

GitHub Pages does not run a dynamic backend. The API is therefore a static file API:

- `api/manifest.json`: API version, dataset version, counts, path templates, and online library package metadata.
- `api/search/index.json`: compact search index. The client downloads it and filters locally.
- `api/substances/by-id/{hash}.json`: one substance detail record.
- `api/interactions/by-substance/{hash}.json`: DDI/DFI rows involving one substance.
- `api/dose-rules/by-substance/{hash}.json`: dose threshold rules involving one substance.
- `api/sources/index.json`: source-layer summary showing which upstreams contributed facts.
- `api/packages/full/manifest.json`: full fused online package metadata and checksum.
- `api/packages/full/fused-online-library.zip`: optional full online library package for review/import tools; local clients do not download it automatically.

Configure the local app with the `/api` base URL, for example:

```text
https://<your-name>.github.io/<repo>/api
```

## Local Boundary

The desktop/mobile app remains local-first. It keeps the original local seed, private journal, and profile storage. The online library is a remote fallback and review source: it can answer misses through static JSON paths, while the full package is only for explicit tooling or future import flows.

## Privacy Boundary

Remote fallback is off by default. When enabled, the browser requests remote static files only after a local miss or when a cached remote substance is used. The remote host can see file requests for the search index and substance IDs. Keep the option disabled if no query should leave the device.

## Large Label Sources

openFDA and DailyMed bulk label archives are too large to keep on the client. The hosted build therefore uses their public search APIs for high-value candidate terms by default. Full bulk archives should be processed by a workstation into normalized EvidenceFact JSON, then placed under `data/optional` for fusion and publication.
