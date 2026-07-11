# Data Architecture

This document is the authoritative reference for where ingredient data, pairing scores, translations, and curation decisions come from. Read this before touching any data file.

---

## Data flow overview

```
FlavorGraph (external, Apache 2.0)
        │
        │  pipeline/flavorgraph_import.py
        ▼
[6,649 ingredients · 110,339 edges · all pairs with score ≥ 0.01]
        │
        │  AI semantic deduplication (one-time, batched)
        │  → pipeline/merges.json  (3,132 merges)
        │
        │  apply_curation_json.py --curation merges.json
        ▼
web/public/pairings.json  ← COMMITTED BASE  (3,517 ingredients)
        │
        │  .github/workflows/deploy.yml
        │  apply_curation_json.py --curation pipeline/curation.json
        ▼
[deployed pairings.json]  (currently ~1,036 ingredients, not committed)
        │
        │  Vite build
        ▼
web/dist/  → GitHub Pages
```

---

## Files and their roles

### `web/public/pairings.json` — the pairing database (committed)

**This is the owned canonical database. Do not regenerate it without explicit sign-off.**

- **3,517 ingredients** after FlavorGraph import + semantic normalisation
- Format: `{ "i": [name, ...], "p": { "idx": [[pairedIdx, score×100], ...] } }`
- Pair scores are NPMI × 100, rounded to integers (range roughly 1–100)
- All pairs from FlavorGraph with score ≥ 0.01 are stored (no top-N cap)
- Keys in `p` are plain string indices (`"0"`, `"1"`, …) — not `"cuisineIdx,idx"`
- Committed and versioned; the deploy workflow reads it as-is

To verify current state:
```bash
python3 -c "
import json
d = json.load(open('web/public/pairings.json'))
pc = [len(v) for v in d['p'].values()]
print(f'{len(d[\"i\"])} ingredients, pairs: min {min(pc)} max {max(pc)} mean {sum(pc)/len(pc):.1f}')
"
```

### `pipeline/curation.json` — manual curation decisions (committed)

Written by the two curation UIs and saved to `main` via GitHub API. Applied at deploy time by `apply_curation_json.py`.

Structure:
```json
{
  "validated": ["ingredient name", ...],
  "deleted":   ["ingredient name", ...],
  "merged":    { "from name": "to name", ... },
  "badPairs":  [["name a", "name b"], ...],
  "lastSaved": "ISO timestamp"
}
```

`badPairs` (issue #46) removes a single edge in both directions at deploy time —
for legitimate co-occurrences that don't belong in a pairing tool. Names are
resolved through merges, so entries survive renames-by-merge. Maintained by
hand (the curation UIs preserve the field but don't edit it).

| Field | Meaning | Count (2026-07) |
|-------|---------|--------------|
| `validated` | Explicitly confirmed as correct — no action taken, just a record | ~1,190 |
| `deleted` | Removed from the deployed ingredient list | 893 |
| `merged` | `from` ingredient is removed; its pairings are absorbed by `to` | 1,591 sources |

**Deployed ingredient count** ≈ **1,036** (drifts as curation continues — derive it by
running `apply_curation_json.py` on a copy rather than trusting this number).
Curation entries referencing names not in the base are silently skipped.

The `merged` map may contain chains (A→B, B→C). `apply_curation_json.py` resolves
chains to their final target at apply time (a chain ending on a deleted or unknown
name means the source is treated as deleted, and a source listed in both `deleted`
and `merged` is deleted). The curation UIs also resolve chains at write time, so
new chains should no longer be created.

### `pipeline/merges.json` — normalisation merges (committed, read-only)

One-time semantic deduplication applied during the original data import. Maps raw FlavorGraph names to normalised canonical names.

```json
{ "2% milk": "milk", "mashed potato": "potato", ... }
```

- 3,132 entries
- Reduced FlavorGraph's 6,649 ingredients to the 3,517 in `pairings.json`
- **Do not modify.** Changes here cannot be replayed safely without regenerating `pairings.json` from scratch.

### `pipeline/flavorgraph_import.py` — original import script

Downloads FlavorGraph nodes and edges CSVs from GitHub, builds `pairings.json`.

- Source: https://github.com/lamypark/FlavorGraph (Apache 2.0)
- Nodes CSV: 6,653 nodes (6,649 ingredient type)
- Edges CSV: 110,339 ingredient-ingredient edges
- Keeps all edges with NPMI score ≥ 0.01 (no top-N cap — **do not add one**)

Run only if rebuilding the base from scratch, then re-apply `merges.json`.

### `web/public/taxonomy.json` — ingredient taxonomy (committed, generated)

Category + base-ingredient mapping for every name in the base `pairings.json`
(issue #41). Consumed by the client for category-aware re-ranking (#43) and
same-base variant suppression (#44).

- Format: `{ "hash brown": {"c": "starch", "b": "potato"}, "cinnamon": {"c": "spice"} }`
- `c` — one of 15 categories (meat, seafood, dairy, egg, vegetable, fruit, herb,
  spice, starch, legume-nut, fat, condiment, sweet, beverage, other)
- `b` — optional culinary parent, only for *derivatives/preparations*
  (apple juice → apple, smoked salmon → salmon). Deliberately NOT for siblings
  (lima bean does not point at bean's siblings) — sibling closeness is handled
  by the category penalty.
- Regenerate with `python pipeline/generate_taxonomy.py` after ingredient
  renames; hand corrections belong in that script's `OVERRIDES` /
  `BASE_OVERRIDES` dicts (they always win over the rules).

### `pipeline/apply_curation_json.py` — curation applicator

Takes a base `pairings.json` and a curation JSON file, applies deletions and merges, writes the result in-place.

Used two ways:
1. **At deploy time** (automatic): applies `pipeline/curation.json` to `web/public/pairings.json`
2. **During data rebuilds** (manual): applies `merges.json` wrapped as a curation envelope

```bash
# Deploy (handled by workflow — do not run manually in normal circumstances):
python pipeline/apply_curation_json.py

# Manual with custom paths:
python pipeline/apply_curation_json.py path/to/curation.json path/to/pairings.json
```

---

## Translations

French ingredient names come from a hardcoded dictionary in two places:

| File | Used by |
|------|---------|
| `web/src/utils/translateFr.ts` | React app |
| `web/public/curate.html` (inline `frDict`) | Curation UI |
| `web/public/merge.html` (inline — not included) | Merge UI (EN only) |

The two copies must be kept in sync manually. Generated originally by `pipeline/generate_translations.py` but not maintained incrementally — edit both files when adding translations.

No external translation API is called at runtime.

---

## Curation UIs

### `web/public/curate.html`

Swipe-card interface for reviewing ingredients one by one. Actions: keep, delete, or merge into another ingredient. Saves to `pipeline/curation.json` on `main` via GitHub API (requires a personal access token with `contents: write`).

### `web/public/merge.html`

Batch merge interface. Groups ingredients by shared key terms (e.g. all squash variants, all potato variants). User selects a canonical (👑) and duplicates (✓), then hits Merge. Saves to the same `pipeline/curation.json`.

Both UIs share `localStorage` key `curate_decisions` and GitHub token `curate_gh_token`.

---

## Deploy workflow

`.github/workflows/deploy.yml` runs on every push to `main`:

1. `python pipeline/apply_curation_json.py` — applies curation to `pairings.json` in-place
2. `npm run build` — Vite build (React app + service worker)
3. Upload `web/dist/` to GitHub Pages

The deployed `pairings.json` is **not committed** — it is rebuilt on every deploy from the committed base + curation decisions.

---

## Invariants — do not break these

1. **`pairings.json` keys are plain string indices** (`"0"`, `"251"`) not `"cuisineIdx,idx"`. The React client (`web/src/db.ts`) reads `p[String(ingredientIdx)]`.

2. **Ingredient names are the join key** between `pairings.json` and `recipes.json`. If a name changes in `pairings.json` it must change in `recipes.json` too.

3. **No top-N truncation on pairs.** All FlavorGraph edges with score ≥ 0.01 are stored. Truncating pairs breaks the leave-one-out outlier detection and the recommendation engine for high-degree ingredients.

4. **`curation.json` is the only file the curation UIs write.** They never modify `pairings.json` directly.

5. **Any change to `pairings.json` ingredient count or names requires explicit owner sign-off.** This is not a routine operation.
