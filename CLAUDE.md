# Flavour Pairing — Project Instructions

## Backlog & feature workflow

- When the user lists feature ideas, create a GitHub issue for each one (repo: `txmnzia/flavour-pairing`) with a clear description, options, and recommended approach.
- Features are prioritised periodically. **Only implement the highest-priority open issue.** Never work ahead.
- Each feature or fix gets its own branch. Never implement on `main` directly.
- **When any change is complete, merge it to `main` and push immediately — do not wait for permission, do not ask.** This applies to features, bug fixes, and copy changes alike.
- Exception: destructive changes (schema changes, removing features, any change to data files) — confirm before merging.
- Branches allow easy rollback — keep them clean and focused on one issue.

## Data architecture — read this first

**`pipeline/DATA.md` is the authoritative reference** for all data files. Read it before touching `pairings.json`, `curation.json`, `merges.json`, or any pipeline script.

Short summary:
- `web/public/pairings.json` — committed pairing database, 3,517 ingredients, all FlavorGraph pairs. **Never truncate, never regenerate without sign-off.**
- `pipeline/curation.json` — manual curation decisions (deleted, merged). Applied at deploy time. Currently produces **~1,036 ingredients** in the live app (drifts as curation continues).
- `pipeline/merges.json` — one-time normalisation merges (6,649 → 3,517). Read-only.
- Deployed ingredient list (~1,036) is derived at build time; no single file lists it.

## Data integrity rules

- **Any change to `pairings.json` ingredient count or names requires explicit owner sign-off.** Always confirm before modifying the ingredient list.
- **Never add a top-N cap to pair storage.** All FlavorGraph pairs with score ≥ 0.01 must be kept.
- Ingredient names are the runtime join key between `pairings.json` and `recipes.json`. A rename in one requires the same rename in the other.
- `pairings.json` keys in `p` must stay as plain string indices (`"0"`, `"251"`), not `"cuisineIdx,idx"`.

## Consistency tests — must always pass

- `python3 pipeline/validate_pairings.py` (data structure, curation, taxonomy, deploy transform) and `npm test` in `web/` (ranking behaviour probes) must pass before merging **any** change to data files, pipeline scripts, or ranking code in `web/src/db.ts`.
- CI enforces this on every push and PR (`.github/workflows/validate.yml`).
- If a probe fails because behaviour changed *intentionally*, update the test in the same commit and explain the reasoning in the commit message — never delete a probe to make it pass.

## Git hygiene

- Commit and push after every working change.
- `web/public/pairings.json` is the owned canonical database — commit it.
- `web/public/pairings.db` is a generated build artifact — do not commit it.
- `web/dist/` is the build output — do not commit it (gitignored).
- `web/package-lock.json` should be kept up to date and committed.

## Curation UIs

- `web/public/curate.html` — swipe-card review (keep / delete / merge)
- `web/public/merge.html` — batch merge of similar ingredient variants
- `web/public/annotate.html` — grade pooled pairing suggestions (0/1/2) for the ranking evaluation; saves to `pipeline/eval/judgments.json` (issue #50)
- `web/public/images.html` — review ingredient photo tiles: delete a tile or replace it (file upload / image URL); saves the WebP + manifest + overrides + credits to `main` via GitHub API (issue #48)

Both save to `pipeline/curation.json` on `main` via GitHub API. Both are excluded from the service worker (`vite.config.ts` `navigateFallbackDenylist`). Adding a new standalone HTML tool requires adding it to that denylist.

## Architecture notes

- **No backend.** Everything is static, deployed to GitHub Pages.
- `web/public/pairings.json` (pairing engine) and `web/public/recipes.json` (recipe catalog, optional) are served as static assets.
- Ingredient names are stored as strings in `recipes.json` (not indices) — the client resolves names → IDs at load time.
- Scoring uses NPMI. Multi-ingredient: average NPMI across selected, minimum coverage = `max(1, round(n * 0.5))`.
- LOO (leave-one-out) highlighting: a selected card turns red if its average NPMI with the other selected ingredients is >1 std dev below the group mean and <50% of the group mean.
- French translations live in `web/src/utils/translateFr.ts` (app) and inline in `curate.html`. Both copies must be kept in sync.
