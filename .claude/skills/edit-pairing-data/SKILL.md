---
name: edit-pairing-data
description: 'Safe procedures for changing the flavour-pairing ingredient data — pipeline/curation.json (delete/merge/badPairs/resurrect), web/public/pairings.json (base corrections), taxonomy via pipeline/generate_taxonomy.py, and why pipeline/merges.json is untouchable. Use when asked to delete, merge, or rename an ingredient; add a badPair or remove a wrong pairing edge; resurrect a deleted ingredient; run ingredient/pairing audits (issues #49, #51); or for ANY request that would change the ingredient count or names in pairings.json.'
---

# Safely editing the pairing data

Read `pipeline/DATA.md` before any edit — it is the authoritative reference for file
formats and invariants. This skill gives the procedures and the guardrails.

## The owner sign-off gate — read this first

This is the hardest rule in the repo (CLAUDE.md, DATA.md invariant 5):

- **Any change to `web/public/pairings.json` ingredient count or names requires explicit
  owner confirmation BEFORE merging.** Not routine. No exception for automated pipelines.
- More broadly, CLAUDE.md's merge-immediately rule has one exception: **destructive changes
  (schema changes, removing features, any change to data files) — confirm before merging.**
  `curation.json` and `pairings.json` are both data files: prepare the change on a branch,
  run validation, then ask the owner before merging to `main`.
- The owner is `txmnzia` (samuelouden@gmail.com).

What does NOT need sign-off: reading data, running validators, preparing a branch,
regenerating `taxonomy.json` from an unchanged base (deterministic, reviewable diff).

## Where does the change belong? (decision guide)

Prefer `curation.json` for everything it can express — it is **reversible** (applied at
deploy time; the committed base is never touched) and it is what the whole toolchain expects.

| You want to… | Edit | Notes |
|---|---|---|
| Remove an ingredient from the app | `pipeline/curation.json` → `deleted` | reversible; preferred |
| Collapse duplicate/variant names | `pipeline/curation.json` → `merged` | prefer the UIs (`merge.html`, `curate.html`) — they enforce the `recordMerge` discipline; hand-edit only with the chain rules below |
| Remove ONE wrong pairing edge (e.g. "tuna–muffin") | `pipeline/curation.json` → `badPairs` | hand-maintained; the UIs preserve but never edit it (issue #46) |
| Bring back a deleted ingredient | remove its name from `deleted` | see resurrection procedure |
| Fix a wrong category or base link | `OVERRIDES` / `BASE_OVERRIDES` dicts inside `pipeline/generate_taxonomy.py`, then regenerate | **never hand-edit `web/public/taxonomy.json`** — it is generated; the next regeneration wipes hand edits |
| Correct the base data itself (wrong score, base-level bad edge, new ingredient from an approved enrichment) | `web/public/pairings.json` | ONLY with owner sign-off; symmetric-edge rules below |
| Rename an ingredient | full join-key checklist below | rare; sign-off; touches ~6 places |
| Change normalisation of the original import | **nowhere** | `pipeline/merges.json` is read-only: it was applied once to produce the 3,517-name base and cannot be replayed without regenerating `pairings.json` from scratch |

## curation.json semantics (exact, from `pipeline/apply_curation_json.py`)

Structure (counts as of 2026-07-11 — **they drift; derive, don't trust**:
`python3 -c "import json;c=json.load(open('pipeline/curation.json'));print({k:(len(v) if not isinstance(v,str) else v) for k,v in c.items()})"`):

```json
{
  "validated": ["…"],          // 1,190 — record-only, NO deploy effect
  "deleted":   ["…"],          // 894  — removed from the deployed app
  "merged":    {"from": "to"}, // 1,588 — from's edges absorbed by to
  "badPairs":  [["a", "b"]],   // 0    — edge removed in both directions
  "lastSaved": "ISO timestamp"
}
```

Applied at deploy time by `apply_curation_json.py`. The exact rules:

- **Chain resolution:** `merged` may contain chains (A→B, B→C). The applicator follows the
  chain to the final target (A→C). The UIs also resolve at write time, so new chains
  shouldn't appear — but hand edits can create them; the validator's cycle check catches loops.
- **Delete wins:** a name present in BOTH `deleted` and `merged` is deleted — its edges are
  NOT redirected (AUDIT.md §8 defined this precedence).
- **Dead-end chains:** a chain ending on a deleted or unknown name means the source is
  treated as deleted (its edges vanish, deliberately).
- **Merge score conflict:** when a source's edges land on a target that already has that
  partner, the **max** score wins.
- **badPairs:** each `["name a", "name b"]` removes that edge in BOTH directions at deploy.
  Names are resolved through the (chain-resolved) `merged` map, so an entry written against
  a merged-away name still lands on its final target. Entries whose names resolve to nothing
  are **silently skipped** — write against current canonical base names and verify (below).
- **Unknown names are silently skipped** everywhere: a `deleted`/`merged` entry that doesn't
  exactly match a base `i` name does nothing, with no warning. The validator tolerates ≤5
  such orphans (2 exist today: `fresh tortellini`, `napa cabbage leaf`).
- **`validated` is record-only** — it changes nothing at deploy; it is the curation UIs'
  "reviewed, keep" bookkeeping.
- **Preserve unknown fields.** Any tool or script that rewrites curation.json must carry
  fields it doesn't manage (the UIs preserve `badPairs`; your script must too).

## Procedures

Work on a branch (`git checkout -b <issue>-<slug>`). All python commands run from repo root.

### Delete an ingredient

1. Confirm the exact base name:
   `python3 -c "import json; i=json.load(open('web/public/pairings.json'))['i']; print([n for n in i if 'SEARCH' in n])"`
2. Add the exact string to the `deleted` array in `pipeline/curation.json` (names are
   lowercase; must match byte-for-byte or the entry is silently ignored).
3. Validate (see Verification). Watch for a new `deployed: every ingredient has >=1 pair`
   failure — deleting a hub can orphan its partners.
4. STOP: confirm with the owner before merging (data-file change).

For bulk review work, prefer `web/public/curate.html` (the owner's swipe UI) over hand edits.

### Merge duplicate ingredients

Prefer `web/public/merge.html` / `curate.html` — their shared `recordMerge` helper resolves
targets through existing merges, re-points earlier merges, and refuses self-merges, cycles,
and deleted targets (AUDIT.md §2: hand-grown chains once destroyed 126 ingredients' edges).

Hand-editing `merged` in `pipeline/curation.json` — replicate that discipline:

1. Resolve your intended target through the existing map first: if `"target"` is itself a
   key in `merged`, use its final destination instead.
2. Never merge into a name in `deleted` (source would be silently deleted, not merged).
3. Never create `"x": "x"`.
4. Re-point earlier merges: any existing entry `"a": "yourSource"` must become `"a": "yourTarget"`.
5. Validate — the self-merge and cycle checks will catch mistakes.

### Remove a wrong pairing edge (badPairs)

1. Append `["name a", "name b"]` to `badPairs` in `pipeline/curation.json` — current
   canonical names, order irrelevant (both directions are removed).
2. Verify the edge is actually gone from the deployed output:

   ```bash
   python3 pipeline/validate_pairings.py --deployed-out /tmp/deployed.json
   python3 - <<'EOF'
   import json
   d = json.load(open('/tmp/deployed.json'))
   idx = {n: i for i, n in enumerate(d['i'])}
   a, b = idx['name a'], idx['name b']          # <-- your two names
   print('a->b present:', any(p == b for p, _ in d['p'].get(str(a), [])))
   print('b->a present:', any(p == a for p, _ in d['p'].get(str(b), [])))
   EOF
   ```

   Both must print `False`. If the edge is still there, the names didn't resolve (typo, or
   not the canonical form) — remember bad entries are skipped silently.
3. Owner confirmation before merging.

### Resurrect a deleted ingredient

1. Remove the name from `deleted` in `pipeline/curation.json`. That's the whole mechanism —
   deletion is reversible precisely because the base was never touched.
2. Check the name is not ALSO a key in `merged`: delete-wins precedence was masking the
   merge, so removing the delete revives it as a *merge source* (edges redirect to the
   target instead of the ingredient reappearing). Remove it from `merged` too if you want
   it back as itself.
3. Validate; the deployed count rises. This changes the live ingredient list → owner
   confirmation before merging.

### Rename an ingredient (join-key checklist — sign-off required)

Ingredient names are the runtime join key across every data surface. A rename in one place
is a rename in ALL places, in one commit:

1. `web/public/pairings.json` — the entry in `i`. **Same position** — never reorder `i`;
   `p` references indices.
2. `web/public/recipes.json` — no such file exists in the repo today (recipe feature is
   dormant, issue #5). If one has appeared since, rename there too.
3. Translations — the EN key in **both** copies: `web/src/translations/fr.json` and
   `web/public/translations/fr.json`; plus the inline `frDict` in `web/public/curate.html`
   (a single `const frDict = {…}` line, ~line 268).
4. Taxonomy — move any `OVERRIDES` / `BASE_OVERRIDES` entries keyed by (or pointing at) the
   old name in `pipeline/generate_taxonomy.py`, then regenerate:
   `python3 pipeline/generate_taxonomy.py` (rewrites `web/public/taxonomy.json`; commit both).
5. Images — the slug changes: rename `web/public/ingredient-images/<old-slug>.webp` to the
   new slug and update the slug in `web/public/ingredient-images/manifest.json` (slug logic:
   `ingredientSlug()` in `web/src/utils/ingredientImage.ts` = `slugify()` in
   `pipeline/fetch_images.py`); also update `pipeline/image_credits.json` if the name appears
   there. Alternatively re-run the `fetch-images.yml` workflow for the new name.
6. `pipeline/curation.json` — every occurrence of the old name: `deleted`, `merged` (keys
   AND values), `badPairs`, `validated`. Orphaned entries are silently skipped, so a missed
   one doesn't crash — it just stops working.
7. Validate everything (taxonomy coverage + unknown-refs checks will catch most misses).
8. Owner sign-off before merging — a rename IS a name change to `pairings.json`.

### Correct the base data in pairings.json (rare — sign-off FIRST)

Only for genuine base-data corrections (or an approved enrichment merge — see the
`enrich-corpus` skill). Never for curation-expressible changes. Rules:

- The file is compact single-line JSON — edit programmatically, never in an editor. Write with
  `json.dump(data, f, ensure_ascii=False, separators=(',', ':'))` (matches the pipeline).
- **Symmetric edges:** every edge exists in both `p[str(a)]` and `p[str(b)]` with the SAME
  integer score. Any add / remove / re-score is TWO edits, one per direction.
- **Keep lists sorted by score descending** (the applicator and client both assume it).
- Scores are integers ≥ 1 (= round(NPMI × 100)). No zeros, no floats.
- **New ingredients append at the END of `i`** — never insert or reorder; existing indices
  must not move (`p` references them; stable indices keep diffs reviewable).
- **Update `meta.ingredients`** whenever `len(i)` changes (stale-meta incident, AUDIT.md §9).
- **Never remove an entry from `i`** to delete an ingredient — that shifts every later index
  and corrupts `p`. Deletion is what `curation.json` is for.
- `p`-keys stay plain string indices (`"0"`, `"251"`) — never `"cuisineIdx,idx"`.
- After a base edit, taxonomy coverage must still hold — regenerate if names were added.

### Fix a taxonomy category or base link

1. Edit `pipeline/generate_taxonomy.py`: `OVERRIDES` dict (name → category, ~line 231) or
   `BASE_OVERRIDES` dict (name → culinary parent, ~line 301). Overrides always win over rules.
2. `b` is ONLY for derivatives/preparations (smoked salmon → salmon, apple juice → apple) —
   deliberately never for siblings (lima bean does not point at bean); sibling closeness is
   the category penalty's job.
3. Valid categories (exactly these 16): meat, seafood, dairy, egg, vegetable, fruit, herb,
   spice, starch, legume-nut, fat, condiment, sweet, beverage, alcohol, other.
4. Regenerate: `python3 pipeline/generate_taxonomy.py` — commit the script AND the
   regenerated `web/public/taxonomy.json` together.
5. Validate; also run `npm test` in `web/` — taxonomy changes move ranking probes
   (category penalties, base suppression).

## Verification

Run the full suite — see the `validate-data` skill for interpretation:

```bash
python3 pipeline/validate_pairings.py        # repo root
cd web && npm install && npm test            # npm install first time only
```

For edge-level changes, additionally inspect the deployed output via
`--deployed-out` (exact recipe in the badPairs procedure above).

If a `web/src/db.test.ts` probe fails because your change *intentionally* altered behaviour:
update the probe in the same commit with reasoning in the commit message — never delete a
probe (protocol in the `validate-data` skill).

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| Curation entry has no effect, no error | name doesn't byte-match a base `i` entry (typo, singular/plural, or it was merged away) | look the name up in `i`; for badPairs use the final canonical name |
| `edge symmetry` FAIL after a base edit | edited one direction only | mirror the edit in `p[str(partner)]` |
| `meta.ingredients` FAIL | changed `len(i)` without updating meta | set it to `len(i)` |
| `merge map is cycle-free` FAIL | hand merge created a loop | pick the surviving canonical; point all cycle members at it |
| Merged ingredient's edges vanished instead of transferring | chain ends on a deleted/unknown target, or source also in `deleted` (delete wins) | fix the chain target / remove the delete entry |
| Resurrected ingredient doesn't reappear | still a key in `merged` | remove it from `merged` too |
| `taxonomy: covers every base name` FAIL | added/renamed a base name without regenerating | `python3 pipeline/generate_taxonomy.py` |
| `deployed: every ingredient has >=1 pair` FAIL after deletions | you deleted all partners of a survivor (AUDIT.md §12) | delete the orphan too (with confirmation) or undo one deletion |
| badPairs array vanished after using a script/UI | rewriter dropped fields it doesn't manage | restore from git; make the tool preserve unknown fields |
| Mojibake (Ã©…) in curation.json after a UI save | bare `atob()` decode regression (AUDIT.md §4) | restore from git; ensure the UI decodes via `TextDecoder` |

## Hard rules

- **Never change pairings.json ingredient count or names without explicit owner sign-off** —
  the live app, curation history, translations, images, and probes all hang off this list.
- **Never truncate pair lists or add a top-N cap** — an import script once shipped
  `TOP_N = 50`, which would have silently destroyed ~90% of edges for high-degree
  ingredients and broken LOO detection (AUDIT.md §3). All edges with score ≥ 0.01 stay.
- **Never modify `pipeline/merges.json`** — it was applied once (6,649 → 3,517) and cannot
  be replayed; editing it changes nothing except lying about history.
- **Never hand-edit `web/public/taxonomy.json`** — regenerated by `generate_taxonomy.py`;
  hand edits evaporate on the next run. Fixes go in the script's override dicts.
- **Never change `p`-keys away from plain string indices** — a legacy workflow that emitted
  `"cuisineIdx,idx"` keys was deleted as a footgun (AUDIT.md §11); the client reads
  `p[String(idx)]`.
- **Never delete an ingredient by editing `i`** — index shift corrupts every pairing list.
- **Never commit `web/public/pairings.db` or `web/dist/`** — build artifacts (AUDIT.md §10).
- **Never let a curation.json rewrite drop fields** the tool doesn't understand (`badPairs`
  is hand-maintained and easy to lose).

## When to STOP and ask the owner (txmnzia)

- BEFORE merging any curation.json or pairings.json change to `main` (data files are the
  explicit exception to the merge-immediately rule).
- BEFORE any edit that changes the pairings.json ingredient count or names — get explicit
  sign-off, not just a lack of objection.
- Before schema changes to any data file.
- When an audit (issues #49/#51) produces a batch of proposed deletions/merges — present
  the list; don't apply unilaterally.
