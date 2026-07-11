# Corpus Enrichment Runbook

**Audience:** the agent (or human) who will enrich the pairing database with a
new recipe corpus — e.g. French recipes to fix the app's US-corpus skew
(issue #47). I'm writing this as the departing data scientist: everything you
need is here or linked; nothing lives in my head. Read `DATA.md` first — it is
the authority on file formats and invariants, and this document assumes it.

**What "enrichment" means here:** ingest a corpus of recipes, map its
ingredients onto the app's canonical ingredient space, compute NPMI pairing
scores from its co-occurrences, and merge those edges into
`web/public/pairings.json` so under-represented combinations (duck+orange,
leek+cream, shallot+tarragon) exist and score honestly.

---

## 0. Design decisions you should not re-litigate (and why)

1. **Merge policy is `max`, not weighted average.** We do not have FlavorGraph's
   underlying counts — only its final NPMI×100 integers — so no statistically
   honest cross-corpus average exists. The rule "an edge is as strong as its
   strongest cultural context" (`score = max(existing, new)`) is heuristic but
   has three properties we rely on: it never degrades an existing score, it is
   idempotent (re-running an ingestion is a no-op), and it means **corpus size
   does not need to rival Recipe1M** — a 30k-recipe French corpus influences
   the table wherever its edges are stronger or new, full stop.
2. **Volume does NOT rebalance; ranking does.** Even a perfect French corpus
   will not push duck+orange into duck's top-9 if the ranking math buries it —
   that is issue #45 (NPMI rarity debias), a separate lever. Enrichment fixes
   *missing/weak edges*; #45 fixes *what you see first*. Budget for both.
3. **New ingredient indices append at the END of `i`.** Never re-order or
   re-index existing entries — `p` references indices, and stability makes
   diffs reviewable.
4. **All thresholds in one place** (`CONFIG` at the top of the ingestion
   script). Every number in this document is a starting value, not scripture —
   but change them in config, never inline.
5. **Provenance sidecar is mandatory** (`pipeline/corpora/<corpus>/manifest.json`
   + edge provenance). It is what makes per-cuisine overlays (#47 end-state)
   and rollback possible later. Skipping it saves an hour and costs the
   project the cuisine-filter feature.

---

## 1. Phase A — Corpus acquisition

### Decision tree

1. **A ready dataset exists → use it.** Check, in order: Kaggle ("marmiton",
   "french recipes"), HuggingFace datasets, academic corpora. A dumped dataset
   beats scraping on every axis (speed, legality, reproducibility).
2. **Owner provides a site to scrape → build an adapter** (see below).
3. Never redistribute scraped content: raw corpus files live in
   `pipeline/corpora/<corpus>/raw/` which is **gitignored**; only manifests,
   mapping tables and derived edge lists are committed.

### Scraping rules (if scraping)

- Respect `robots.txt`; identify with a plain UA string; **1 request / 2–5 s**,
  single-threaded; cache every fetched page to disk on first fetch so a re-run
  never re-hits the site; stop and report if the site starts serving CAPTCHAs.
- One adapter per site (`pipeline/adapters/<site>.py`), all emitting the same
  normalized JSONL (schema below). The pipeline downstream of the JSONL must
  not know or care where recipes came from.

### Normalized recipe schema (JSONL, one recipe per line)

```json
{"id": "marmiton-12345", "title": "Blanquette de veau", "lang": "fr",
 "ingredients_raw": ["1 kg de veau", "250 g de champignons de Paris", "20 cl de crème fraîche"],
 "source": "marmiton", "url": "https://..."}
```

### How much volume is significant?

The statistic that matters is **per-pair co-occurrence support**, not raw
corpus size (because merge policy is `max` — see §0.1). NPMI stabilises at
roughly ≥ 20 co-occurrences per pair. A classic pairing appears in ~0.5–3 % of
a cuisine's recipes; median recipe ≈ 9 mapped ingredients ≈ 36 pairs.

| Corpus size | What you can trust (support ≥ 20) | Verdict |
|---|---|---|
| 5 k recipes | only pairs in ≥ 0.4 % of recipes — headline classics only | proof-of-concept |
| 10–30 k | most canonical cuisine pairs | minimum viable |
| **30–80 k** | long-tail regional pairs too | **target** (Marmiton ≈ 70 k+) |
| > 200 k | diminishing returns; consider raising support threshold | unnecessary |

---

## 2. Phase B — Ingredient line parsing (French specifics)

Turn `"250 g de crème fraîche épaisse"` into the phrase `crème fraîche`.

1. Strip leading quantity + unit: numbers (incl. `1/2`, `1,5`), then unit from:
   `g, kg, mg, l, cl, ml, dl, c. à soupe, c. à café, cuillère(s) à soupe/café,
   cs, cc, sachet(s), pincée(s), gousse(s), tranche(s), feuille(s), brin(s),
   branche(s), botte(s), boîte(s), pot(s), verre(s), tasse(s), pièce(s),
   filet(s), zeste(s), noix (de beurre), morceau(x), rondelle(s), poignée(s)`.
2. Strip the partitive that follows: `de, d', du, des, de la`.
3. Cut trailing preparation clauses: anything after a comma, and trailing
   participles/qualifiers from a stoplist (`haché, émincé, râpé, coupé, fondu,
   battu, tamisé, écrasé, ciselé, épluché, dénoyauté, surgelé, en dés,
   en tranches, en morceaux, facultatif, selon goût…`).
4. Lowercase; trim; collapse whitespace. **Keep accents** at this stage — the
   matching stage handles both accented and folded forms.
5. Drop lines that map to non-ingredients (`eau` → keep actually: `water` is
   canonical; but drop `sel, poivre`? **No — keep everything**; frequency
   thresholds and mapping rules decide, not the parser).

Emit `(recipe_id, phrase)` pairs. Parsing must be pure/deterministic — all
judgement is deferred to the mapping phase.

---

## 3. Phase C — Mapping phrases → canonical ingredients

Canonical space = the 3,517 names in `web/public/pairings.json` `i` (English).
This is the phase where projects die; do it as a **deterministic cascade with
a model stage at the end**, and measure every stage.

### Assets you already have

- **Inverted French dictionary:** `web/src/translations/fr.json` maps
  EN→FR for 3,653 entries covering 2,892/3,517 canonical names. Invert it
  (FR→EN). Where two canonicals share a French name, prefer the one with more
  pairs in `pairings.json`.
- **The suffix/prefix grammar** in `web/src/utils/translateFr.ts` (huile de X,
  jus de X, X en poudre, frais/haché/séché…) — reuse its patterns in reverse.
- **`pipeline/merges.json`** — after mapping to an English name, always pass it
  through `merges.json` (raw-variant → canonical) and then through
  `curation.json`'s `merged` map, chain-resolved. This keeps you aligned with
  every normalisation decision ever made.

### The cascade (each phrase stops at its first hit; log the stage)

| Stage | Rule |
|---|---|
| C1 | exact match against inverted fr.json |
| C2 | match after fold: lowercase, strip accents, singularise (FR plural rules: `-s`, `-x`, `-aux→-al`) on BOTH sides |
| C3 | grammar reverse: peel `PREFIX_FR`/`COLOR_FR`/`SUFFIXES` patterns from translateFr.ts, map the base via C1/C2, reassemble the English form, check it is canonical (e.g. `jus de citron` → base `citron`→`lemon` → `lemon juice` ∈ canon) |
| C4 | direct English match: the phrase already is/contains a canonical name (borrowed words: `curry`, `ketchup`) |
| C5 | **model stage** — batch the survivors (see contract below) |
| C6 | unmapped → count it; if its recipe-frequency < `NEW_MIN_FREQ` (default 30), discard; else it becomes a NEW-ingredient candidate from C5 |

### Model-stage contract (C5)

Batch 50–100 phrases per call. For each phrase, with its occurrence count and
3 sample source lines as context, the model returns exactly one of:

- `MAP <canonical name>` — must be byte-identical to an entry in the canonical
  list you provide in the prompt (validate; reject and retry the row if not);
- `NEW <english name>` — only if frequency ≥ `NEW_MIN_FREQ` **and** no
  canonical is a culinary match. The proposed name must be lowercase English,
  singular, and must NOT collide with an existing canonical under the
  keyTerms/singularise similarity used by `merge.html` (validate
  programmatically; a collision downgrades it to `MAP` of the collided name);
- `DISCARD` — brand names, compound prepared dishes ("pâte à tarte maison"),
  non-food.

Determinism guards: temperature 0; sort inputs; cache responses keyed by
phrase so re-runs are stable; commit the full mapping table
(`corpora/<corpus>/mapping.json`) — it IS the reproducibility artifact.

### Acceptance gates for the mapping (no human row-by-row curation, but hard metrics)

- ≥ 90 % of ingredient *occurrences* (weighted by frequency) mapped by C1–C4.
  If the deterministic stages map less, fix the parser/grammar before letting
  the model mop up — a model doing the bulk means silent drift.
- Self-audit: sample 100 random mappings stratified by stage, have the model
  re-derive them blind, require ≥ 97 % agreement; disagreements get re-decided
  with both answers shown.
- NEW list: expect **dozens, not hundreds** (French cuisine mostly uses
  ingredients the canon already has). > 100 NEW candidates almost certainly
  means the parser is leaking qualifiers or the cascade is missing a grammar
  rule. Investigate before proceeding.

### NEW-ingredient obligations (each one you admit costs downstream work)

For every NEW ingredient: add an EN→FR entry to **both** copies of fr.json
(`web/src/translations/fr.json`, `web/public/translations/fr.json`) and to the
inline `frDict` in `web/public/curate.html` (sync rule in DATA.md); regenerate
`taxonomy.json` (`python pipeline/generate_taxonomy.py`) and check the new
names didn't land in `other`/wrong category — add OVERRIDES if needed; emoji
coverage is optional (fallback 🌿 is acceptable).

---

## 4. Phase D — Computing pairs (NPMI)

Reference implementation survives in git history — salvage with:
`git show f7d37e1:pipeline/process.py` (function `compute_npmi`). The formula:

```python
import math
def npmi(count_ab, count_a, count_b, n_recipes):
    p_ab = count_ab / n_recipes
    p_a  = count_a  / n_recipes
    p_b  = count_b  / n_recipes
    pmi  = math.log(p_ab / (p_a * p_b))
    return pmi / -math.log(p_ab)          # ∈ (-1, 1]
```

Rules:

- Count each ingredient **once per recipe** (dedupe the mapped set per recipe
  before pairing — French recipes often list butter twice).
- `MIN_INGREDIENT_FREQ = 30` recipes; `MIN_COOCCURRENCE = 20`; keep pairs with
  `npmi ≥ 0.01`. **Never** add a top-N cap (invariant 3; we removed exactly
  such a bug once already).
- Store symmetric (edge present in both ingredients' lists, same score),
  score as `round(npmi * 100)`.
- Output: `corpora/<corpus>/edges.json` = `[[nameA, nameB, scoreInt], …]` —
  **names, not indices** (names are the stable join key; indices are
  per-build).

---

## 5. Phase E — Merging into pairings.json

Write `pipeline/enrich_pairings.py` (does not exist yet; ~100 lines):

1. Load base `pairings.json`, `edges.json`, `curation.json`.
2. Resolve each edge's names through `merges.json` + chain-resolved
   `curation.merged`. If either endpoint is in `curation.deleted` → **drop the
   edge** (the owner deleted that ingredient; a new corpus does not overrule
   curation — do not resurrect).
3. Endpoint not in canon and not NEW-approved → drop (log it).
4. NEW ingredients: append to the END of `i`.
5. Edge exists → `score = max(old, new)`. Edge new → insert, **both
   directions**, keep each list sorted by score desc.
6. Write provenance: `corpora/<corpus>/provenance.json` listing every edge that
   was added or raised (old → new score). This file is the future per-cuisine
   overlay's input and the review artifact.
7. Update `meta.ingredients`; leave everything else in `meta` untouched.

**Gate: modifying `pairings.json` (count or scores) requires explicit owner
sign-off — no exception for automated pipelines** (CLAUDE.md data rule). The
sign-off package = the validation report from Phase F, not raw diffs.

---

## 6. Phase F — Validation (run before asking for sign-off)

Commit a permanent `pipeline/validate_pairings.py` usable by ALL future data
work, not just this one:

**Structural** (hard failures): `p` keys are plain string indices; every index
in range; no self-pairs; no duplicate names in `i`; full symmetry (a↔b same
score); every score int ≥ 1; deployed transform (`apply_curation_json.py` on a
copy) still runs and every deployed ingredient keeps ≥ 1 pair.

**Golden probes — the point of the exercise** (run through the deploy
transform + the client ranking rules in `web/src/db.ts`, i.e. penalties, damp,
decay, base suppression — replicating them in the validator is fine, they are
~40 lines): after a French ingestion assert at least e.g. `duck→orange`,
`leek→cream` (crème fraîche), `shallot→tarragon`, `mussel→shallot`,
`veal→mushroom` exist with score ≥ 25 and rank ≤ 20. Fix the probe list per
corpus before running, not after seeing results.

**Regression probes:** the curated expectations that already hold —
`apple→cinnamon` in top-9, no drinks wall for `soy sauce`, no protein pile for
`pork`, `tuna` shows `english muffin` not `muffin` — must all still pass.
Max-merge should make regressions rare; a regression usually means a mapping
error created a false heavyweight edge.

**Distributional:** report edge-count and score histograms before/after, count
of raised vs added edges, top-20 most-raised edges (eyeball these — mapping
errors surface here as absurd pairs).

---

## 7. Phase G — Ship

1. Feature branch → commit `pairings.json`, mapping table, manifest,
   provenance, edges, any fr.json/taxonomy updates. Raw corpus stays
   gitignored.
2. Owner sign-off on the validation report (hard gate, see §5).
3. Merge to main → deploy workflow applies curation and publishes
   automatically. Verify the Actions run is green and spot-check the live app
   (remember the service worker: pairings.json is NetworkFirst, so a refresh
   picks it up; the app shell may need a second visit).
4. Rollback = `git revert` of the data commit; nothing else holds state.

---

## 8. Pitfalls that have already bitten this project once

- **A top-N cap silently truncated pairs** (import script, fixed 2026-07).
  Never cap. The validator checks for suspicious uniform list lengths.
- **Merge chains** (A→B→C) destroyed 126 ingredients' edges at deploy until
  `apply_curation_json.py` learned to chain-resolve. Always chain-resolve when
  consuming `curation.merged`.
- **Merge conflations** create absurd edges (`english muffin`→`muffin` made
  "tuna pairs with muffin"). When mapping, prefer DISCARD over a semantically
  wrong MAP — a lost data point is recoverable, a wrong edge is poison that
  needs manual `badPairs` cleanup.
- **Ingredient names are the join key everywhere** (pairings, recipes.json,
  translations, taxonomy, curation). A rename in one place is a rename in all.
- **`curation.json` has fields the UIs don't manage** (`badPairs`) — any tool
  that rewrites it must preserve unknown fields.
- **The deploy transform rewrites pairings.json in place on the runner** —
  never point validation at a file the workflow already mutated.

## 9. What I would do differently (advice, not instruction)

1. **Do #45 (rarity debias) in the same milestone.** Enrichment without
   ranking reform under-delivers: your beautiful new French edges will rank
   below hyper-distinctive corpus artifacts, and the owner will conclude the
   ingestion "didn't work". The candidate-relative normalization in issue #45
   also makes golden probes much easier to pass honestly.
2. **Treat overlays (#47 end-state) as the second ingestion's feature, not the
   first's.** First ingestion: max-merge into the global table + provenance.
   Once two corpora exist, the provenance files already contain everything a
   per-cuisine filter needs — build the UI then.
3. **Keep the validator and probe list as permanent CI** for any PR touching
   `pairings.json` — a one-day investment that converts every future data
   change from "trust me" to "checks passed".
4. If scraping proves brittle, a 10k-recipe dataset TODAY beats a 70k scrape
   in three weeks. Ship the minimum viable corpus, learn from the probe
   results, iterate.

## 10. Execution checklist (copy into your task list)

- [ ] A: corpus acquired (dataset preferred); manifest committed; raw gitignored
- [ ] B: parser built; spot-check 50 random parsed lines
- [ ] C: cascade run; stage metrics ≥ gates; mapping.json committed; self-audit ≥ 97 %
- [ ] C: NEW list reviewed (< ~100); translations ×3 locations; taxonomy regenerated
- [ ] D: edges.json computed (support thresholds, no cap, symmetric)
- [ ] E: enrich_pairings.py merged edges; provenance.json written
- [ ] F: validate_pairings.py all green; golden + regression probes pass; report generated
- [ ] G: owner sign-off on report → merge → deploy green → live spot-check
