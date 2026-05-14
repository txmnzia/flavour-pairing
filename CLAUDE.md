# Flavour Pairing — Project Instructions

## Backlog & feature workflow

- When the user lists feature ideas, create a GitHub issue for each one (repo: `txmnzia/flavour-pairing`) with a clear description, options, and recommended approach.
- Features are prioritised periodically. **Only implement the highest-priority open issue.** Never work ahead.
- Each feature gets its own branch: `feature/<short-name>`. Never implement on `main` directly.
- When a feature is complete and working, merge it to `main` immediately without asking — don't wait for permission.
- Exception: destructive changes (schema changes, removing features) — confirm before merging.
- Branches allow easy rollback — keep them clean and focused on one issue.

## Git hygiene

- Commit and push after every working change.
- `web/public/pairings.json` is the **owned canonical database** — commit it. It was normalized once from FlavorGraph and is maintained directly.
- `web/public/pairings.db` is a generated build artifact — do not commit it.
- `web/package-lock.json` should be kept up to date and committed.

## Curating ingredients by hand

`pipeline/ingredients.txt` is the canonical allowlist of all ingredients in the dataset.
To remove unwanted ingredients:
1. Edit `pipeline/ingredients.txt` on GitHub — delete or `#`-comment any line you don't want.
2. Ask Claude: **"Rebuild pairings from ingredients.txt"**
3. Claude will run `pipeline/apply_ingredients.py` locally, push the result to `feature/real-data`, and trigger a redeploy.

The script automatically removes pairing entries that reference deleted ingredients.

## Generating real recipe data

Run this once locally after `pip install -r pipeline/requirements.txt`:

```bash
python pipeline/process.py \
  --source huggingface \
  --limit 500000 \
  --output /tmp/pairings.db \
  --json-output web/public/pairings.json
```

Then commit `web/public/pairings.json` — the deploy workflow detects it and skips the demo generator.
To use a local RecipeNLG CSV instead: `--source csv --input data/full_dataset.csv`.

## Data integrity — ingredient name consistency

**Whenever an ingredient name changes** (rename, merge, deduplicate — e.g. "tomatoes" → "tomato"), update ALL three locations in the same commit:

1. **`pairings.json`** (`i` array + `p` keys) — the pairing engine
2. **`recipes.json`** (`r[*][1]` ingredient name lists) — recipe catalog
3. **`pipeline/generate_demo.py` `RECIPES` list** — source of truth for demo recipes

Failure to keep these in sync silently drops recipe↔ingredient linkages (the client joins by name at runtime). Normalization scripts (`normalize_v4.py` and future variants) must apply the same rename/merge map to `recipes.json` in addition to `pairings.json`.

**Footer counts** are auto-derived from `ingredients.length` (runtime) and `dataMeta.recipes` (from `pairings.json` `meta.recipes`, set by the pipeline). They update automatically after a rebuild — no manual edit needed.

## Architecture notes

- **No backend.** Everything is static, deployed to GitHub Pages.
- Two data files served as static assets: `web/public/pairings.json` (co-occurrence engine) and `web/public/recipes.json` (recipe catalog — optional, app degrades gracefully if missing).
- Ingredient names are stored as **strings** in `recipes.json` (not indices), so the file is self-contained and robust to index reordering in `pairings.json`. The client resolves names → IDs at load time.
- `pairings.json` is committed as an owned database (no longer regenerated at build time). The deploy workflow just builds the React app and uploads it.
- `recipes.json` is optional and generated separately.
- Scoring uses NPMI. Multi-ingredient: average NPMI across selected, minimum coverage = `max(1, round(n * 0.5))`.
