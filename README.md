# Flavour Pairing

Discover what ingredients go well together. Select one or more ingredients and get ranked pairing suggestions based on recipe co-occurrence data from FlavorGraph.

**Live app:** https://txmnzia.github.io/flavour-pairing/

## What it does

- Select ingredients → ranked suggestions scored by NPMI (normalised pointwise mutual information)
- Multi-ingredient mode: suggests ingredients that pair well with the whole selection
- Leave-one-out highlight: flags a selected ingredient red if it is the statistical outlier in the group
- French translation toggle
- Recipe matching (if `recipes.json` is present)

## Architecture

No backend. Everything is a static site deployed to GitHub Pages via GitHub Actions.

- **`web/`** — React + Vite + Tailwind frontend
- **`web/public/pairings.json`** — the pairing database (committed, owned)
- **`pipeline/curation.json`** — manual curation decisions (committed, owned)
- **`.github/workflows/deploy.yml`** — builds the app and applies curation at deploy time

See [`pipeline/DATA.md`](pipeline/DATA.md) for the full data architecture.

## Running locally

```bash
cd web
npm install
npm run dev
```

The dev server serves `web/public/pairings.json` directly.

## Curation UIs

Both pages are excluded from the service worker and load standalone:

| Page | URL | Purpose |
|------|-----|---------|
| `curate.html` | `/curate.html` | Review ingredients one-by-one: keep / delete / merge |
| `merge.html` | `/merge.html` | Batch-merge similar ingredient variants |

Both save decisions to `pipeline/curation.json` on `main` via GitHub API. Changes take effect on the next deploy.
