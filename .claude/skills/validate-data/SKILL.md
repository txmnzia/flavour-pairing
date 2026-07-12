---
name: validate-data
description: Runs and interprets the flavour-pairing consistency suite (python3 pipeline/validate_pairings.py plus npm test in web/) and explains what every check failure means. Use BEFORE merging any change that touches web/public/pairings.json, pipeline/curation.json, web/public/taxonomy.json, any pipeline script, or ranking code in web/src/db.ts; when the CI workflow "Data & ranking consistency" (.github/workflows/validate.yml) fails; when a vitest probe in web/src/db.test.ts fails; when you need the current deployed ingredient count; or when asking "did I break the data?".
---

# Validate the pairing data and ranking behaviour

The consistency suite has two layers. Both must pass before merging any change to data
files, pipeline scripts, or ranking code in `web/src/db.ts` (CLAUDE.md rule; CI enforces it
via `.github/workflows/validate.yml` on every push to `main`, every PR, and manual dispatch —
CI also runs `npm run build` afterwards).

1. **Structural validator** — `pipeline/validate_pairings.py` (Python 3, stdlib only).
   Checks the committed base, the curation file, the taxonomy, then runs the REAL deploy
   transform (`pipeline/apply_curation_json.py`) on a temp copy and checks the deployed output.
2. **Behaviour probes** — `npm test` in `web/` (vitest). Exercises the real ranking engine
   (`web/src/db.ts`) against the real deployed data.

Background docs: `pipeline/DATA.md` (data authority), `AUDIT.md` (incident history — most
validator checks exist because of a specific incident there).

## Before you start

- Run from the repo root for the Python layer; from `web/` for the npm layer.
- `python3` must be on PATH — **for both layers** (the vitest global setup shells out to it).
- First npm run on a fresh clone: `npm install` inside `web/` (node_modules is gitignored).
- No other setup. The validator never modifies committed files (it works on a temp copy).

## Procedure

1. From the repo root:

   ```bash
   python3 pipeline/validate_pairings.py
   ```

   Success looks like a list of `[ok  ]` lines ending in `All consistency checks passed.`
   (exit 0). Failure prints `[FAIL]` lines and a `N FAILURE(S):` summary (exit 1).

2. From `web/`:

   ```bash
   npm install    # first time only
   npm test       # = vitest run
   ```

   Expected while ranking annotation (issue #50) is below threshold:
   `Test Files  1 passed | 1 skipped (2)` — the skip is `web/src/eval.test.ts` and is normal
   (see "The vitest layer" below). Any *failed* test is a blocker.

3. Both green → the change is structurally and behaviourally safe. This does NOT replace
   owner sign-off gates for data changes — see the `edit-pairing-data` skill.

## What each validator check means

`validate_pairings.py` runs four groups. Every check maps to a concrete corruption mode:

### Structure checks (run twice: on `base` = committed pairings.json, and on `deployed` = post-curation output)

| Check line | Asserts | A failure implies |
|---|---|---|
| `no duplicate names` | every entry of `i` is unique | a merge/rename created a name collision; the name→index join is now ambiguous |
| `all p-keys are plain in-range indices` | every key of `p` is a digit string `< len(i)` | someone reintroduced the dead v1 `"cuisineIdx,idx"` format, or deleted `i` entries without rekeying `p` — the client reads `p[String(idx)]` and will silently miss data |
| `no self-pairs` | no ingredient pairs with itself | a merge collapsed two names but left their mutual edge |
| `no out-of-range partner indices` | every `[partnerIdx, score]` points inside `i` | `i` was shortened without rewriting `p` |
| `all scores are integers >= 1` | scores are NPMI×100 ints | floats or zeros leaked in from a new computation script |
| `no duplicate partners within a list` | each partner appears once per list | a merge combined two lists without deduping |
| `edge symmetry` | a→b exists ⟺ b→a exists **with the same score** | a hand edit or script changed one direction only — LOO and reverse lookups now disagree |
| `no top-N cap signature` | no length appears for >25% of lists (when mode length >10) | some script truncated pair lists (the `TOP_N = 50` incident, AUDIT.md §3). Find and remove the cap; the data must be regenerated from an untruncated source |
| `meta.ingredients matches actual count` | `meta.ingredients == len(i)` | a script edited `i` without updating `meta` (the stale-6649 incident, AUDIT.md §9) |

### Curation checks (`pipeline/curation.json`)

| Check line | Asserts | A failure implies |
|---|---|---|
| `badPairs is a list of [nameA, nameB] string pairs` | shape of the hand-maintained edge blacklist | a tool rewrote curation.json and mangled a field it doesn't manage |
| `no self-merges` | no `"x": "x"` in `merged` | hand edit bypassed the UIs' `recordMerge` guard |
| `merge map is cycle-free` | following `merged` always terminates | A→B, B→A style loop — would hang naive resolvers; pick one canonical name and break the cycle |
| `<=5 entries reference names missing from base` | deleted/merged names still exist in base `i` | a base rename/regeneration orphaned curation entries (they are silently skipped at deploy — the curation decision stops having any effect). A small residue is tolerated (2 known orphans as of 2026-07) |

### Taxonomy checks (`web/public/taxonomy.json`)

| Check line | Asserts | A failure implies |
|---|---|---|
| `covers every base name` | every name in `i` has a taxonomy entry | an ingredient was added/renamed without rerunning `python3 pipeline/generate_taxonomy.py` — category penalties and same-base suppression silently degrade |
| `all categories valid` | `c` ∈ the 16 known categories | typo in `OVERRIDES` inside `generate_taxonomy.py` |
| `base chains are cycle-free` | following `b` links terminates | contradictory `BASE_OVERRIDES` entries — the client's `resolveBase()` would loop |

### Deploy-transform checks

| Check line | Asserts | A failure implies |
|---|---|---|
| `deploy transform runs clean` | `apply_curation_json.py` exits 0 on a copy | curation.json is malformed or the applicator regressed — the real deploy would fail the same way |
| `deployed: every ingredient has >=1 pair` | no orphan ingredients post-curation | deletions/merges removed all of an ingredient's partners (AUDIT.md §12 — five such orphans were found once). Delete the orphan too, or resurrect a partner |
| `deployed: ingredient count N within sanity band [800, 2500]` | curation didn't mass-delete or stop applying | a corrupted `merged`/`deleted` list, or curation silently not matching base names at scale |

## `--deployed-out` and deriving the deployed ingredient count

The deployed ingredient list exists in no committed file — it is derived at build time.
Any written-down count (~1,036 in CLAUDE.md/DATA.md; 1,038 on 2026-07-11) is **approximate
and drifts with every curation edit**. Derive it, don't trust it:

```bash
python3 pipeline/validate_pairings.py --deployed-out /tmp/deployed.json
python3 -c "import json; print(len(json.load(open('/tmp/deployed.json'))['i']))"
```

The validator also prints it inline: `deployed: N ingredients, N pairing lists`.
The `--deployed-out` file is the exact JSON the live app would serve — use it for any
"is edge X present after curation?" question.

## The vitest layer (`npm test` in `web/`)

- `web/test/global-setup.ts` builds `web/test/.deployed.json` by copying the base and running
  `pipeline/apply_curation_json.py` on it via `python3` (`execFileSync("python3", …)`). If
  `python3` is missing from PATH, every test errors before running.
- `web/src/db.test.ts` — **ranking behaviour probes**. Each probe encodes behaviour the owner
  has signed off on (e.g. "pork's top-9 contains no other protein", "potato never suggests
  hash brown", "tuna suggests english muffin, not muffin", "apple surfaces cinnamon in its
  top-9"). They run the real `db.ts` engine against the real deployed data — no replica to drift.
- `web/src/eval.test.ts` — **metrics report, not a gate** (issue #50). Scores the current
  formula against owner judgments in `pipeline/eval/judgments.json` (written by
  `web/public/annotate.html`; the pool lives at `web/public/eval/pool.json`). It uses
  `describe.skipIf` and skips cleanly whenever the judgments file is missing **or** holds
  fewer than `MIN_JUDGMENTS = 200` graded pairs. When it does run, it prints Precision@9,
  Discovery@9, Recall@36, nDCG@9 per dev/holdout split — it asserts almost nothing. Issue #50
  step 3 turns the metrics into assertions once baseline + targets are agreed; until then a
  metrics change is information, not a failure.

### Probe-update protocol (when a db.test.ts probe fails)

1. Decide honestly: is the failure a **bug** or an **intentional behaviour change**?
2. Bug → fix the code/data. The probe is right.
3. Intentional change → **update the probe in the SAME commit** as the change, and explain
   the reasoning in the commit message (what behaviour changed, why the new expectation is
   correct). Behaviour changes may themselves need owner sign-off — check the
   `edit-pairing-data` skill's gates.
4. **NEVER delete a probe to make the suite pass.** Probes are the owner's signed-off
   expectations; deleting one silently un-signs a decision.

## Failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| `no top-N cap signature` FAIL (mode length spike) | a script truncated pair lists to a fixed N (the removed `TOP_N=50` bug, AUDIT.md §3) | remove the cap from the script; restore the data from git (`git checkout` the file) or regenerate from the untruncated source |
| `meta.ingredients matches actual count` FAIL | script changed `i` without touching `meta` | set `meta.ingredients = len(i)` in the same change |
| `edge symmetry` FAIL | hand edit added/removed/re-scored one direction only | apply the identical edit to the mirror list `p[str(partner)]` |
| `merge map is cycle-free` FAIL | curation.json edited by hand, bypassing the UIs' `recordMerge` guard | chain-resolve manually: pick the surviving canonical, point every cycle member at it |
| `taxonomy: covers every base name` FAIL | ingredient added/renamed without regenerating | `python3 pipeline/generate_taxonomy.py`, commit the regenerated `web/public/taxonomy.json` |
| `deployed: every ingredient has >=1 pair` FAIL | curation removed all partners of a surviving ingredient (AUDIT.md §12) | add the orphan to `curation.json` `deleted` (with owner confirmation), or reverse one of the partner deletions |
| `<=5 entries reference names missing from base` FAIL | base names changed under the curation file | update curation entries to the new names (see the rename checklist in `edit-pairing-data`) |
| `deploy transform runs clean` FAIL | malformed curation.json (bad JSON, wrong types) | inspect the stderr excerpt the check prints; fix the JSON |
| `npm test` errors with `spawn python3 ENOENT` | python3 not on PATH for node | install/expose python3; the deploy workflow has the same dependency |
| `npm test` fails a db.test.ts probe after a data/ranking change | behaviour changed | probe-update protocol above — bug vs intentional |
| eval.test.ts suddenly *runs* instead of skipping | `pipeline/eval/judgments.json` crossed 200 judgments | normal; read the metrics, they don't gate (yet — issue #50) |
| Local green but CI red | CI validates the committed state, not your working tree; or `npm run build` (tsc) fails on a type error the tests don't touch | commit everything the change needs; run `npm run build` in `web/` locally |

## Hard rules

- **Never delete a probe to make the suite pass** — each probe is owner-signed-off behaviour;
  deleting one is silently revoking a product decision.
- **Never weaken a validator check to get green** without understanding the root cause —
  every check exists because the corruption it detects actually happened (see AUDIT.md).
- **Never point validation at a pairings.json the deploy workflow already mutated** — the
  deploy transform rewrites the file in place on the runner; validate the committed file
  (the validator already does this correctly by copying to a temp dir).
- **Never commit `web/test/.deployed.json`, `web/public/pairings.db`, or `web/dist/`** —
  generated artifacts (all gitignored; pairings.db was once committed by accident, AUDIT.md §10).

## When to STOP and ask the owner (txmnzia)

- A validator failure whose only fix changes the `pairings.json` ingredient count or names —
  that fix itself requires explicit sign-off first.
- You believe a validator check or a probe is *wrong* — checks encode owner decisions;
  don't unilaterally change them.
- The deployed count moved outside anything curation activity explains.
