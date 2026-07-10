# Code Audit — July 2026

Full audit of the app: React client, data pipeline, curation UIs, workflows, and
committed data. Findings are ordered by severity. Items marked **fixed** were
resolved in the accompanying commits; the data-file and cleanup items in the last
section were applied after explicit owner sign-off.

## Critical — fixed

### 1. Merge chains silently destroyed pairing data at deploy time
`pipeline/curation.json` contained **126 merge chains** (A→B where B itself is
merged into C, up to 3 hops deep). `apply_curation_json.py` only did single-hop
lookups: a chain source whose target was merged away was **dropped entirely**
instead of being absorbed — its pairing edges vanished from the deployed app.
Example: `beef bouillon → beef broth → beef` meant every `beef bouillon` edge
was lost instead of enriching `beef`.

**Fix:** `apply_curation_json.py` now resolves chains to the final target, with
explicit precedence rules (delete wins over merge; a chain ending on a deleted
or unknown name deletes the source). Verified: the deployed ingredient list is
byte-identical (at the time, 1,041 ingredients), while merge targets recover their missing
edges (`chili` +30 pairs, `beef` +14, `chicken` +9, …).

### 2. Root cause: curation UIs created the chains
- `curate.html`'s merge search and merge suggestions excluded *deleted*
  ingredients but **not already-merged-away ones**, so you could merge X into a
  ghost.
- Neither UI protected the other direction: merging Y into Z when earlier
  decisions already pointed A→Y left A orphaned.

**Fix:** both UIs now share a `recordMerge` helper that resolves the target
through existing merges, re-points earlier merges into the source at the new
target, and refuses self-merges/cycles and deleted targets. Merged-away names
no longer appear as merge candidates.

### 3. `flavorgraph_import.py` had a `TOP_N = 50` cap
Directly contradicts data invariant 3 ("never add a top-N cap") — the committed
base has up to 971 pairs per ingredient, so rerunning the import would have
silently truncated ~90% of edges for high-degree ingredients and broken the
LOO/recommendation engine. **Fix:** cap removed; all pairs ≥ 0.01 kept.

## Bugs — fixed

### 4. Base64 decode corrupted non-ASCII curation data (latent)
Both curation UIs decoded the GitHub API response with bare `atob()`, which
mojibakes any UTF-8 beyond Latin-1 — while the *save* path correctly encoded
UTF-8. Round-tripping a name like `jalapeño` would corrupt `curation.json`.
Currently latent (all names are ASCII today). **Fix:** proper UTF-8 decode via
`TextDecoder` in both files.

### 5. i18n defects in the React app
- `SearchInput` hard-coded the French placeholder `"Chargement…"` during
  loading — shown to English users too. Now localized via App.
- `RecommendationList` showed English-only UI text in French mode ("Group
  harmony", "pairs well with", "more", both empty-state messages) — the
  empty-state strings were even routed through the *ingredient-name*
  translator, which can never translate them. Now localized with a `lang` prop.

### 6. FAQ demo badges contradicted their labels
Demo scores 0.83/0.50/0.14 render as 82/50/14 (badge shows `round(v×99)`) but
the labels claimed 83/49/13. Values adjusted so badge and label agree.

### 7. Browse-list ranking broke on trailing whitespace
In `App.tsx`, filtering used the trimmed query but prefix-ranking used the raw
one, so `"tom "` matched "tomato" without ranking prefix matches first. Both
now use the trimmed query.

### 8. Robustness/doc fixes
- `apply_curation_json.py` no longer crashes (`KeyError`) on a pairings file
  without a `meta` block.
- Conflicting curation entries now have defined semantics: `chicken bouillon
  granule` was in both `deleted` and `merged` — previously its edges were still
  redirected to the merge target; delete now wins.
- Misleading comment in `curate.html`'s `loadFromGH` ("remote merged takes
  precedence" — the code does, correctly, the opposite) fixed.
- `DATA.md`/`CLAUDE.md` counts were stale (claimed 1,081 deployed; actual
  1,041; curation counts drifted too). Updated, with a note that the number
  drifts and how to derive it.

## Data & cleanup items — fixed with owner sign-off (2026-07-10)

### 9. Committed `pairings.json` had stale `meta.ingredients: 6649`
The base holds 3,517 ingredients but its `meta` still said 6,649 (pre-merge
count). **Fixed:** `meta.ingredients` set to 3,517; no other bytes changed.

### 10. `web/public/pairings.db` (2.2 MB) and `sql-wasm.wasm` (0.66 MB) were committed dead weight
`pairings.db` was tracked in git despite `.gitignore` and CLAUDE.md saying it
must not be committed, and nothing in the app references sql.js/sqlite anymore.
Together they were ~2.9 MB of the 4.8 MB deploy. **Fixed:** both removed.

### 11. `generate-pairings.yml` was a loaded footgun
The manual workflow regenerated `pairings.json` from RecipeNLG in the **v1
cuisine-keyed format** (`c` array, `"cuisineIdx,idx"` keys) — running it against
any deployed branch would have broken invariant 1, the app, and both curation
UIs. **Fixed:** workflow deleted along with the legacy RecipeNLG/sqlite scripts
it belonged to (`process.py`, `apply_curation.py`, `apply_ingredients.py`,
`curate.py`, `generate_demo.py`, `ingredients.txt`, `requirements.txt`).
`flavorgraph_import.py`, `apply_curation_json.py`, and
`generate_translations.py` remain the active pipeline.

### 12. Five deployed ingredients had zero pairings
`abalone`, `fried rice`, `hibiscus tea bag`, `root beer concentrate`, `smelt`
ended up with no outgoing pairs after curation (all partners deleted or merged).
**Fixed:** added to `curation.json` `deleted`; the deployed app now has 1,036
ingredients, every one with at least one pairing.

## Notes / accepted behaviour

- **Curation sync is last-writer-wins across devices** (GitHub Contents API,
  SHA read then PUT). Validated/deleted are unioned on load, so real loss
  requires two devices merging concurrently. Acceptable for a single-owner tool.
- **`includeAssets: ["pairings.json", …]` in `vite.config.ts` does not precache
  the data** (precache is ~326 KB; the 1.5 MB JSON is served via the
  NetworkFirst runtime cache instead). Offline works only after first data
  fetch — arguably the right trade-off, but the config line is misleading.
- `recipes.json` is fetched on every load and 404s (no recipe catalog is
  deployed). Handled gracefully by `Promise.allSettled`; the recipe features
  are simply dormant.
- The GitHub token for the curation UIs lives in `localStorage` on a static
  site — fine for a personal tool; don't use a broadly-scoped token.
- `db.ts` "freq" (used for popularity ranking) is the sum of pair scores, not a
  real frequency — works fine as a proxy; just a naming quirk.
- Language choice isn't persisted across reloads and the shell `<html lang>` is
  always `en` — possible future issue, not a defect.
