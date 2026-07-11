---
name: enrich-corpus
description: 'Entry point for enriching the pairing database with a new recipe corpus — acquiring/scraping recipes, mapping ingredients to the canonical space, computing NPMI edges, and merging them into web/public/pairings.json. Use when asked to ingest French or Marmiton recipes (issues #47, #4), add a new cuisine corpus, fix the US-corpus skew, compute pairing scores from recipes, or build per-cuisine overlays. This skill is the routing layer and gate summary; pipeline/ENRICHMENT.md is the full runbook.'
---

# Enrich the pairing database with a new corpus

This skill is deliberately thin. **`pipeline/ENRICHMENT.md` is the complete runbook,
written by the departing data scientist — read it end-to-end BEFORE doing anything, and
treat it as the authority.** This skill exists to route you there, hold the hard numbers
and gates in one glance, and stop you at the points where projects have died before.

Also read first: `pipeline/DATA.md` (file formats + invariants — ENRICHMENT.md assumes it)
and the sibling skills `validate-data` (verification) and `edit-pairing-data` (the
sign-off gate and pairings.json editing rules).

## Before you start

1. Read `pipeline/ENRICHMENT.md` §0 ("design decisions you should not re-litigate") —
   max-merge policy, append-at-end indices, config-only thresholds, mandatory provenance.
   Do not reopen these decisions.
2. Confirm with the owner WHICH corpus and which issue this serves (#47 multi-cuisine,
   #4 Marmiton, or something new). Check the open issues before starting.
3. If scraping is on the table: prefer a ready dataset (Kaggle, HuggingFace, academic).
   Scraping needs the owner's go-ahead on the target site, respects robots.txt, 1 request
   per 2–5 s, and caches every page (ENRICHMENT.md §1).

## Phase checklist (A–G — each phase is a full section in ENRICHMENT.md)

- [ ] **A — Acquire**: dataset preferred over scraping; normalized JSONL schema;
      `pipeline/corpora/<corpus>/manifest.json` committed; raw corpus stays out of git.
- [ ] **B — Parse**: deterministic ingredient-line parser (quantity/unit/partitive
      stripping, French specifics in §2); spot-check 50 random parsed lines.
- [ ] **C — Map** phrases → the 3,517 canonical names in `web/public/pairings.json` `i`:
      deterministic cascade C1–C4 (inverted `web/src/translations/fr.json`, folding,
      grammar reversal from `translateFr.ts`, borrowed words) then model stage C5;
      always pass results through `pipeline/merges.json` + chain-resolved
      `curation.merged`; commit `corpora/<corpus>/mapping.json`.
- [ ] **C (NEW ingredients)**: each admitted NEW name costs translations in 3 places +
      taxonomy regeneration (ENRICHMENT.md §3 "NEW-ingredient obligations").
- [ ] **D — Compute NPMI edges**: dedupe ingredients per recipe; support thresholds below;
      output `corpora/<corpus>/edges.json` as `[[nameA, nameB, scoreInt], …]` —
      names, not indices.
- [ ] **E — Merge** into `pairings.json` via a new `pipeline/enrich_pairings.py`
      (~100 lines, spec in §5); write `corpora/<corpus>/provenance.json`.
- [ ] **F — Validate**: structural suite + golden probes + regression probes +
      distributional report (§6). Fix the golden-probe list BEFORE seeing results.
- [ ] **G — Ship**: feature branch → owner sign-off on the Phase F report → merge →
      deploy green → live spot-check (§7).

## Acceptance gates (hard numbers — starting values; change only in the script's CONFIG)

| Gate | Threshold | Failing it means |
|---|---|---|
| Deterministic mapping (C1–C4) | ≥ 90% of ingredient *occurrences* (frequency-weighted) | fix parser/grammar before letting the model mop up — model-mapped bulk = silent drift |
| Model self-audit (C5) | ≥ 97% agreement on 100 stratified re-derived samples | re-decide disagreements with both answers shown |
| NEW-ingredient list | dozens, NOT hundreds (>100 ⇒ stop) | parser is leaking qualifiers or the cascade is missing a grammar rule — investigate first |
| Ingredient support | `MIN_INGREDIENT_FREQ = 30` recipes | below it, NPMI is noise |
| Pair support | `MIN_COOCCURRENCE = 20` | NPMI stabilises around ≥20 co-occurrences |
| Edge score | keep `npmi ≥ 0.01`, store `round(npmi × 100)`, symmetric both directions | — |
| Top-N cap | **NEVER** | invariant 3; a `TOP_N=50` bug already shipped once and was removed (AUDIT.md §3) |
| Merge policy | `score = max(existing, new)` | no honest cross-corpus average exists (no underlying counts); max never degrades, is idempotent, and frees you from matching Recipe1M's size |
| Provenance | `corpora/<corpus>/provenance.json` mandatory (every edge added or raised, old → new) | skipping it kills the future per-cuisine overlay feature (#47) and rollback review |

## The owner sign-off gate

**Modifying `pairings.json` (ingredient count, names, or scores) requires explicit owner
sign-off — no exception for automated pipelines** (CLAUDE.md data rule; ENRICHMENT.md §5).

The sign-off package is the **Phase F validation report**, not raw diffs: golden probes
(corpus-specific, e.g. duck→orange for a French corpus), regression probes (existing
expectations like apple→cinnamon top-9, tuna→english muffin not muffin), and the
distributional report (edge counts, score histograms, top-20 most-raised edges — mapping
errors surface there as absurd pairs). Owner: `txmnzia` (samuelouden@gmail.com).

## Key references

- **Full runbook**: `pipeline/ENRICHMENT.md` (phases §1–7, pitfalls §8, advice §9,
  execution checklist §10).
- **NPMI reference implementation**: the legacy pipeline survives only in git history —
  `git show f7d37e1:pipeline/process.py`, function `compute_npmi` (line 97 of that
  revision; verified present). The formula is also inline in ENRICHMENT.md §4.
- **Artifact home**: `pipeline/corpora/<corpus>/` — commit `manifest.json`,
  `mapping.json`, `edges.json`, `provenance.json`; the `raw/` subdirectory must be
  gitignored. NOTE (verified 2026-07-11): neither `pipeline/corpora/` nor a gitignore
  entry for it exists yet — the first ingestion must add `pipeline/corpora/*/raw/`
  to `.gitignore` when creating the directory. Never commit or redistribute scraped content.
- **Verification**: the `validate-data` skill (`python3 pipeline/validate_pairings.py`
  + `npm test` in `web/`); Phase F golden/regression probes extend it per corpus.
- **pairings.json editing rules** (symmetric edges, append-at-end, meta.ingredients):
  the `edit-pairing-data` skill, section "Correct the base data in pairings.json".

## Pitfalls (condensed from ENRICHMENT.md §8 — each has already bitten this project)

- **Never add a top-N cap** — the validator detects the uniform-length signature.
- **Always chain-resolve `curation.merged`** when consuming it (A→B, B→C ⇒ A→C);
  single-hop lookups once destroyed 126 ingredients' edges at deploy.
- **Deleted stays deleted**: an edge whose endpoint is in `curation.deleted` is dropped —
  a new corpus never overrules the owner's curation; do not resurrect.
- **Prefer DISCARD over a semantically wrong MAP** — a lost data point is recoverable;
  a wrong edge is poison needing manual `badPairs` cleanup (the "tuna pairs with muffin"
  conflation).
- **Names are the join key everywhere** (pairings, translations, taxonomy, curation,
  image slugs) — a rename in one place is a rename in all (checklist in `edit-pairing-data`).
- **Preserve unknown curation.json fields** in any script that rewrites it (`badPairs`).
- **Never point validation at a pairings.json the deploy runner already mutated** — the
  deploy transform rewrites the file in place on the runner.

## Relation to #47 (multi-cuisine overlays)

- The **first** ingestion is a global max-merge into `web/public/pairings.json` plus a
  provenance sidecar. That's all. Do not build cuisine filtering yet.
- Per-cuisine overlays (`pairings.<cc>.json`, same schema, lazy-loaded) are **the second
  corpus's feature**: once two corpora exist, the provenance files already contain
  everything a cuisine filter needs.
- **Never resurrect the v1 `"cuisineIdx,idx"` key format** — a legacy workflow emitting it
  was deleted as a loaded footgun (AUDIT.md §11). Overlays are separate files with plain
  string-index keys, never a key-format change.
- Budget for issue #45 (rarity debias) alongside enrichment — new edges that rank below
  corpus artifacts read as "the ingestion didn't work" (ENRICHMENT.md §9.1).

## Hard rules

- **Read ENRICHMENT.md before acting** — this skill is a map, not the territory; every
  phase has specifics (French parsing rules, model-stage contract, enrich script spec)
  that live only there.
- **No pairings.json modification without owner sign-off on the Phase F report** — the
  hardest gate in the repo.
- **No top-N cap, ever** — breaks LOO and high-degree recommendations (invariant 3).
- **No committed raw corpus** — legal exposure; only manifests, mappings, and derived
  edge lists are committed.
- **No provenance, no merge** — provenance is what makes overlays and rollback possible.
- **All thresholds live in the ingestion script's CONFIG** — never inline magic numbers.
- **New ingredient indices append at the END of `i`** — never reorder or re-index.

## When to STOP and ask the owner (txmnzia)

- Before scraping any site (target choice, legality, politeness budget).
- If the deterministic-mapping gate (<90%), self-audit gate (<97%), or NEW-list gate
  (>100 candidates) fails — do not push through with lowered thresholds.
- Before Phase E touches `pairings.json`, and again at Phase G with the validation report.
- If golden probes still fail after an honest ingestion — the fix may be ranking (#45),
  not more data; that is a prioritisation call, not yours.
