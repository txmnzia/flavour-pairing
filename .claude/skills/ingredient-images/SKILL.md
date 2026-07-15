---
name: ingredient-images
description: 'Run and fix the ingredient image pipeline (pipeline/fetch_images.py, fetch-images.yml workflow, issue #48) — Wikipedia photos turned into 256×256 transparent tiles. Use when an ingredient image is missing or wrong, when adding images for new ingredients, for ghost/transparent tile problems, image licensing/attribution questions, or when running or debugging the "Fetch ingredient images" workflow and the ingredient-images-assets branch.'
---

# Ingredient images (issue #48)

Photo tiles for the recommendation cards. **Images are assets, not pairing
data** — they never affect scoring, are safe to regenerate at any time, and do
not fall under the pairings.json sign-off gate.

> **Quality pass / re-ranking:** to audit tile quality and replace low-quality
> images by ranking *all* images in each article (not just the lead) and gating
> on a quality score, follow **`pipeline/IMAGE_RANKING_RUNBOOK.md`**. That is the
> entry point for the issue-#48 image-quality work: it needs a session with
> Wikimedia network egress, uses `pipeline/rank_images.py` to collect candidates,
> and records picks in `image_overrides.json` (`{"file":…}` / `{"skip":true}`) or
> via the `scan` mode described below. Audit scores live in
> `pipeline/image_audit.csv`.

## The flow

For every ingredient live in the deployed app (`pairings.json` names minus
`curation.json` deletes and merge sources — computed by `live_ingredients()`
in the script), `pipeline/fetch_images.py`:

1. Resolves a Wikipedia article: override → exact title → search fallback
   (search hits are flagged `"via search: <title>"` for review).
2. Takes the article's lead image (PageImages API) and checks its license via
   imageinfo/extmetadata. Keeps only free licenses (CC0 / CC BY / CC BY-SA /
   public domain / GFDL / …); anything matching `nc|nd|fair use|non-free` is
   rejected.
3. Downloads a 512 px thumbnail, removes the background with rembg (u2net
   model), trims to the alpha bounding box, centers on a transparent square
   (subject fills at most `SUBJECT_FILL = 0.80`), and saves a 256×256 WebP to
   `web/public/ingredient-images/<slug>.webp`.
4. **QC gate — rejects "ghost cutouts".** Two checks in `process_image()`:
   - degenerate cutout: alpha bbox smaller than 2% of the image area → reject
   - final tile: fraction of solid pixels (alpha ≥ 200) below **4%** → reject.
     Source comment: "Good tiles measure >=0.13 solid, duds ~0.00 — reject
     below 0.04." Rejected images are reported as
     `"background removal produced no subject"` and the ingredient stays on
     the emoji fallback.
5. `finalize()` regenerates `manifest.json` from the `.webp` files actually on
   disk, plus the credits, report, and attributions page.

Ingredients without a usable image simply keep the emoji fallback — a miss is
not an error.

## File inventory — generated vs hand-edited

| File | Status |
|------|--------|
| `web/public/ingredient-images/<slug>.webp` | **generated** (committed) — the tiles |
| `web/public/ingredient-images/manifest.json` | **generated** — `{generated, count, slugs}`; the client checks `slugs` before rendering an `<img>` |
| `pipeline/image_credits.json` | **generated** — attribution source of truth: file, page_title, license, artist, description_url per ingredient |
| `web/public/attributions.html` | **generated from image_credits.json** — the public credits page (excluded from the SW like the curation tools) |
| `pipeline/image_fetch_report.json` | **generated** — last run's `misses` and `flags` (review this after every run) |
| `pipeline/image_overrides.json` | **HAND-EDITED** — the only file you edit. Format: `{ "<ingredient name>": {"title": "Wikipedia article title"} }` or `{ "<ingredient name>": {"skip": true} }` |

Never hand-edit a generated file; re-run the script instead. Note: as of
2026-07-11 the committed manifest has `count: 0` (no tiles merged to `main`
yet) — the number drifts; check `manifest.json` rather than trusting this.

## The slug join key — two implementations, must stay byte-identical in behaviour

The slug joins ingredient names to image files. It is implemented twice; a
divergence silently breaks image lookup for affected names.

`pipeline/fetch_images.py`:

```python
def slugify(name: str) -> str:
    """Must stay identical to ingredientSlug() in web/src/utils/ingredientImage.ts."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower())
    return s.strip("-")
```

`web/src/utils/ingredientImage.ts`:

```ts
export function ingredientSlug(name: string): string {
  return name
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}
```

If you change one, change the other in the same commit and re-generate the
manifest. Slug collisions between live ingredients are flagged by the script
in the report under `flags._slug_collisions`.

## Emoji fallback semantics (client side)

- `useIngredientImageUrl()` in `web/src/utils/ingredientImage.ts` lazily
  fetches `ingredient-images/manifest.json`; it returns a URL only when the
  ingredient's slug is in `manifest.slugs`.
- `web/src/components/IngredientTile.tsx` renders the `<img>` when a URL
  exists (with an `onError` fallback), otherwise the emoji from
  `web/src/utils/ingredientEmoji.ts` on a hash-derived colour background.
- Therefore: **tiles and manifest must be committed together.** A slug in the
  manifest without its `.webp` produces broken/blank tiles; a `.webp` missing
  from the manifest is simply never shown.
- Service worker caching (`web/vite.config.ts`): manifest is
  StaleWhileRevalidate, tiles are CacheFirst (90 days) — after changing an
  existing tile's content, users may see the old one until cache expiry;
  prefer fixing via a re-fetch (new bytes, same slug is fine, but know the
  cache exists when "it still looks wrong" is reported).

## Before you start

1. Read the "Ingredient images (issue #48)" section of `pipeline/DATA.md`.
2. Decide where to run:
   - **Normal path: the manual GitHub workflow** `.github/workflows/fetch-images.yml`
     ("Fetch ingredient images", `workflow_dispatch`). It installs
     `requests pillow "rembg[cpu]"` on Python 3.11, runs the script, and
     pushes results to the **`ingredient-images-assets`** branch for review —
     **it never touches `main`** (and force-pushes that branch each run).
     Workflow inputs: `limit` (max ingredients, default `"0"` = all) and
     `force` (boolean, re-fetch existing).
   - **Local run** is possible with the same deps and network access to
     `en.wikipedia.org` + `upload.wikimedia.org`
     (`pip install requests pillow "rembg[cpu]"`); dev sandboxes may block
     those hosts, which is exactly why the workflow exists.
3. Runs are **incremental**: an ingredient whose
   `web/public/ingredient-images/<slug>.webp` already exists is skipped unless
   `--force` is given. New ingredients (from curation or enrichment) just need
   a re-run.

## Procedure: add / refresh images (bulk)

1. Trigger the workflow: GitHub → Actions → "Fetch ingredient images" →
   Run workflow (`limit` = 0 for all, or a small number to trial), or:
   ```bash
   gh workflow run fetch-images.yml -f limit=0 -f force=false
   ```
2. Wait for the run (up to 180 min for a full pass), then review the
   `ingredient-images-assets` branch:
   ```bash
   git fetch origin ingredient-images-assets
   git diff --stat main...origin/ingredient-images-assets
   git show origin/ingredient-images-assets:pipeline/image_fetch_report.json | python3 -m json.tool | head -80
   ```
   Check `misses` (no image — fine), and `flags`: `via search:` entries
   (verify the article matches the ingredient), `full-frame cutout`
   (coverage > 0.95 — rembg may have kept the whole photo),
   `_slug_collisions`, `_stale_files` (tiles for since-curated-away names —
   harmless, listed for cleanup).
3. Spot-check a sample of the new `.webp` tiles visually (open them, or run
   the app against the branch).
4. Merge `ingredient-images-assets` into `main` (a normal merge — images are
   assets, no data sign-off needed) and push. The deploy workflow ships them.

## Procedure: fix a single wrong image

1. Add or edit the entry in `pipeline/image_overrides.json`:
   ```json
   { "sage": { "title": "Salvia officinalis" } }
   ```
   or, if no acceptable image exists, `{ "sage": { "skip": true } }` (the
   ingredient reverts to its emoji; an existing tile must be deleted by hand —
   `skip` only prevents fetching).
2. Commit the override on a branch, like any change (CLAUDE.md: never work on
   `main` directly; it is non-data config, so it merges without sign-off),
   then re-fetch just that ingredient with force:
   ```bash
   python3 pipeline/fetch_images.py --only "sage" --force
   ```
   (`--only` is repeatable for several names.) Locally if network allows;
   otherwise run the workflow with `force=true` — note the workflow has no
   `--only` input, so a workflow-based single fix re-fetches everything
   force=true (slow) or you add the tile locally.
3. `finalize()` rewrites the manifest, credits, report, and attributions page
   automatically — commit the tile together with all four.

## Verification

```bash
# Manifest is consistent with the tiles on disk
python3 - <<'EOF'
import json, pathlib
d = pathlib.Path("web/public/ingredient-images")
m = json.loads((d / "manifest.json").read_text())
disk = sorted(p.stem for p in d.glob("*.webp"))
assert m["slugs"] == disk and m["count"] == len(disk), (m["count"], len(disk))
print(f"OK: {len(disk)} tiles, manifest matches disk")
EOF

# Every credited ingredient has a free license recorded
python3 -c "import json; c=json.load(open('pipeline/image_credits.json')); \
bad=[k for k,v in c.items() if not v.get('license')]; print('no-license entries:', bad)"

# Data pipeline untouched (images never affect scoring)
python3 pipeline/validate_pairings.py
cd web && npm test && npm run build
```

Then load the app (`npm run dev` in `web/`, or the deployed site), search an
ingredient with a new tile, and confirm the photo renders; pick one without a
tile and confirm the emoji fallback renders.

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| Ghost / nearly-invisible tile shipped | QC gate passed a marginal cutout (solid-alpha just above 4%) | Add an override to a better-contrast article, `--only "<name>" --force`; if no photo works, `{"skip": true}` and delete the tile. |
| `"background removal produced no subject"` in report | rembg gutted a low-contrast subject; QC gate (<4% solid alpha, or bbox <2%) rejected it | Same as above — override to an article with a clearer lead photo. |
| Wrong picture for an ingredient (wrong Wikipedia article) | Ambiguous name; exact-title or search resolution picked the wrong page (e.g. "date", "game", "punch") | Add `{"title": "..."}` to `pipeline/image_overrides.json`, re-fetch with `--only ... --force`. |
| `"license not free: ..."` in misses | Lead image is fair-use/NC/ND | Override to another article, or skip. Never weaken `license_ok()` / `FREE_LICENSE_RE`. |
| `"no wikipedia lead image"` | Article has no PageImage, or none found | Override to a concrete article title, or accept the emoji. |
| Image in manifest but 404 / blank in app | Manifest and tiles committed out of sync, or slug functions diverged | Re-run the script (finalize rebuilds the manifest from disk); diff `slugify` vs `ingredientSlug`. |
| New ingredient shows emoji although "images were done" | Incremental run predates the ingredient | Just re-run the workflow — only missing tiles are fetched. |
| `flags._stale_files` in report | Tiles remain for ingredients since deleted/merged by curation | Harmless; delete the listed `.webp` files and re-run finalize (any run does this) when cleaning up. |
| Workflow ends "No new images — nothing to push." | Everything already fetched and unchanged | Not an error. |
| Local run: connection errors to wikipedia | Sandbox blocks the hosts | Use the workflow — that is its purpose. |
| Tile updated but users still see the old image | SW CacheFirst on `ingredient-images/*.webp` (90 days) | Expected; clears on cache expiry or SW cache reset. |

## Hard rules

- **The workflow must never push image results to `main`.** It pushes to
  `ingredient-images-assets` for human review first — rembg output and
  search-resolved articles are too error-prone to ship blind.
- **Never hand-edit generated files** (`manifest.json`, `image_credits.json`,
  `attributions.html`, `image_fetch_report.json`, the tiles). The next run
  overwrites them; the only durable manual input is `image_overrides.json`.
- **`attributions.html` must stay generated from `image_credits.json`.**
  Free licenses (CC BY, CC BY-SA, GFDL) legally require attribution — a tile
  without its credit entry is a license violation, not just a style problem.
- **Never weaken the license gate** (`license_ok()` — rejects `nc|nd|fair
  use|non-free`). NC/ND images cannot be shipped in this app.
- **Never change `slugify()` without changing `ingredientSlug()` identically
  in the same commit** — the slug is the join key between names and files.
- **Never remove or lower the QC gate** (<4% solid alpha) without evidence:
  it exists because rembg produced fully transparent "ghost cutouts" that
  looked like blank tiles in the app.
- **Images never touch pairing data.** If an image task seems to require
  renaming an ingredient, stop — that is a `pairings.json` join-key change
  (owner sign-off; see the edit-pairing-data skill).

## When to STOP and ask the owner (txmnzia, samuelouden@gmail.com)

- Regenerating and merging tiles is routine — no sign-off needed.
- STOP if a fix requires renaming an ingredient in `pairings.json` (join key
  across pairings/taxonomy/translations/curation/slugs — owner gate).
- STOP before relaxing the license policy or shipping any image whose license
  you cannot verify.
