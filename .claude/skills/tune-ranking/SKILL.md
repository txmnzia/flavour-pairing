---
name: tune-ranking
description: 'Understand, debug, and change how the flavour-pairing app ranks ingredient suggestions (the scoring pipeline in web/src/db.ts). Use when asked "why does X suggest Y", "why is Y not suggested for X", "Y should rank higher/lower", when tuning ranking constants (SELF_PENALTY, GLOBAL_DAMP, DIVERSITY_DECAY, rarity clamp), when a ranking probe in web/src/db.test.ts fails, or for the ranking-evaluation work of issues #50 and #53 (pool.json, annotate.html, judgments.json, eval.test.ts metrics).'
---

# Tune the suggestion ranking

Everything that determines what the app suggests lives in ONE file: `web/src/db.ts`.
There is no server-side ranking, no replica of the formula anywhere else. The tests in
`web/src/db.test.ts` encode owner-signed-off behaviour; the evaluation kit
(issue #50) measures the formula against the owner's graded judgments.

Line numbers below are correct as of 2026-07-11 — they drift. Anchor by symbol name,
not line number, when the file has changed.

## Before you start

1. Read `web/src/db.ts` in full (~340 lines). Every knob is there, each with a comment
   explaining the incident that created it.
2. Read `web/src/db.test.ts` — these probes are the contract. Know which ones your
   change could touch BEFORE you change anything.
3. Know which data the engine actually runs on: the DEPLOYED data (base + curation),
   not the committed `web/public/pairings.json`. Build it:
   ```bash
   # from repo root
   python3 pipeline/validate_pairings.py --deployed-out /tmp/deployed.json
   ```
   (Running `npm test` in `web/` also builds it, at `web/test/.deployed.json`, via
   `web/test/global-setup.ts` — requires `python3` on PATH.)
4. Know which view is live: the app (`web/src/App.tsx`) renders **category swimlanes**
   via `getRecommendationsByCategory` (LANE_N = 12). The blended grid
   (`getRecommendations`) is exercised by `db.test.ts` and `eval.test.ts`. Both consume
   the same `scoreCandidates()` — see Hard rules.

## The scoring pipeline, stage by stage

All in `web/src/db.ts`, inside `scoreCandidates()` (~line 194) unless noted.
Scores in `pairings.json` are NPMI × 100 integers; the engine divides by 100, so raw
edge scores are 0.01–1.0.

**Stage 1 — coverage gate** (~line 201):
`minCoverage = Math.max(1, Math.round(n * 0.5))` where n = number of selected
ingredients. A candidate must have an edge to at least that many of the selected.
(n=1 → 1, n=2 → 1, n=3 → 2, n=4 → 2, n=5 → 3.)

**Stage 2 — same-base variant suppression** (issue #44, `resolveBase()` ~line 169,
applied ~line 234): follow taxonomy `b` chains (`web/public/taxonomy.json`,
`{c: category, b?: base}`) to the root; drop any candidate whose base equals the base
of ANY selected ingredient. This is why potato never suggests hash brown, and orange
zest never suggests orange.

**Stage 3 — score = (sum/n) × rarityFactor × categoryPenalty** (~line 236–242):

- `sum/n` = average raw NPMI across the selected ingredients the candidate covers
  (missing edges contribute 0 — coverage < n drags the average down).
- `categoryPenalty()` (~line 180), issue #43. Uses the candidate's taxonomy category
  vs the set of selected categories:
  - `SELF_PENALTY` (candidate shares a category with a selected ingredient):
    `meat: 0.35, seafood: 0.35, spice: 0.45, beverage: 0.4, alcohol: 0.4, fruit: 0.5,
    fat: 0.5, starch: 0.55, sweet: 0.7, condiment: 0.7, "legume-nut": 0.7, herb: 0.75,
    dairy: 0.8, vegetable: 1, egg: 1, other: 1`.
    WHY: co-occurrence rewards clusters (spice blends, cocktails, mixed-meat dishes);
    a suggestion engine should surface complements. Another protein next to a protein
    is nearly useless (0.35); vegetables combine freely (1).
  - Cross-sets: `PROTEIN = {meat, seafood}` → 0.35 (surf & turf is the exception, not
    the suggestion); `DRINKS = {alcohol, beverage}` → 0.4.
  - `GLOBAL_DAMP = { alcohol: 0.6 }` — applied ALWAYS, whatever is selected. WHY: the
    corpus is full of cocktail recipes; without this, alcohol walls out fruit/aromatic
    suggestions (the "lemon → 9 liqueurs" incident).
- `rarityFactor()` (~line 156), issue #45. NPMI structurally favours *distinctive*
  co-occurrence: niche aromatics (galangal, median edge 37) crush ubiquitous partners
  (garlic, median 12). Fix: a robust z-score of this pair's average score against the
  CANDIDATE's own edge-score distribution:
  `z = (avgScore×100 − median) / max(IQR, 5)`, clamped to
  `[RARITY_FLOOR 0.25, RARITY_CAP 1.5]`. Stats are built once per data load
  (`getRarityStats()`, median and IQR of each candidate's ×100 scores).
  - **Disable in the live app with `?ranking=raw`** — `RARITY_ENABLED` (~line 138)
    reads `location.search` at module load. Use it to isolate rarity effects.

**Stage 4a — blended grid** (`getRecommendations`, ~line 249): greedy diversity
selection. At each step pick the candidate with the best
`score × DIVERSITY_DECAY^(already-shown count of its category)`, `DIVERSITY_DECAY = 0.8`.
WHY: stops three near-identical drinks (wine / rice wine / sake) monopolising the
first page. The DECAYED score is what's returned, clamped `Math.min(eff, 1)`.

**Stage 4b — swimlanes** (`getRecommendationsByCategory`, ~line 285, issue #52): same
sorted candidates grouped by category, pure score inside a lane (grouping already
guarantees diversity), max `topPerCategory` (app passes 12), lanes ordered by their
strongest candidate so penalised categories sink rather than disappear. Scores clamped
≤ 1 the same way.

**Badge rendering**: the UI shows `Math.round(clampedScore * 99)` on a 0–99 scale —
`ScoreBadge` in `web/src/components/RecommendationList.tsx` (~line 25) and the FAQ demo
badges in `web/src/components/FAQ.tsx` (~line 6). This is why scores are clamped to
≤ 1 in stage 4. AUDIT.md §6: FAQ labels once contradicted the badge math — if you
change badge math, update FAQ demo values/labels in the same commit.

**Outside the pipeline — LOO / group harmony** (`computeLooScores`, ~line 307): for
each selected ingredient, the average over the others of
`max(edge x→y, edge y→x)`. **No penalties, no rarity, no decay — ever.** The red-chip
outlier rule lives in `computeOutlierIds` in `web/src/components/RecommendationList.tsx`
(~line 155): skip if group mean < 0.05; a chip is an outlier when its LOO score is
`< mean − std` AND `< mean × 0.5`.

Also: `getAllIngredients().freq` is the SUM of an ingredient's pair scores — a
popularity proxy used for browse-list ordering, not a real frequency (AUDIT.md notes).

## Procedure A — debug "why is Y (not) suggested for X"

1. Build the deployed data (see Before you start). Confirm both names exist in it —
   the committed base has ~3,517 names but only ~1,038 survive curation (drifts;
   the validator prints the current count).
2. Run this trace (verified working from repo root; edit SEL/CAND/DEPLOYED):

   ```bash
   python3 - <<'EOF'
   import json
   SEL, CAND = "lemon", "honey"
   DEPLOYED = "/tmp/deployed.json"          # from validate_pairings.py --deployed-out
   d = json.load(open(DEPLOYED))
   tax = json.load(open("web/public/taxonomy.json"))
   idx = {n: i for i, n in enumerate(d["i"])}
   sid, cid = idx[SEL], idx[CAND]

   # 1. raw edge (score x100 int; the engine divides by 100)
   edge = dict((a, s) for a, s in d["p"][str(sid)]).get(cid)
   print(f"raw edge {SEL}->{CAND}: {edge}")
   if edge is None:
       raise SystemExit("no edge: candidate can never appear for this single selection")

   # 2. base chains (same-base suppression, #44)
   def base(n):
       seen = {n}
       while True:
           b = tax.get(n, {}).get("b")
           if not b or b in seen: return n
           seen.add(b); n = b
   print(f"bases: {SEL}->{base(SEL)}  {CAND}->{base(CAND)}  suppressed={base(SEL)==base(CAND)}")

   # 3. category penalty (mirror of db.ts SELF_PENALTY / PROTEIN / DRINKS / GLOBAL_DAMP)
   SELF = {"meat":.35,"seafood":.35,"spice":.45,"beverage":.4,"alcohol":.4,"fruit":.5,
           "fat":.5,"starch":.55,"sweet":.7,"condiment":.7,"legume-nut":.7,"herb":.75,
           "dairy":.8,"vegetable":1,"egg":1,"other":1}
   PROTEIN, DRINKS = {"meat","seafood"}, {"alcohol","beverage"}
   scat, ccat = tax.get(SEL,{}).get("c"), tax.get(CAND,{}).get("c")
   damp = 0.6 if ccat == "alcohol" else 1
   if ccat == scat: pen = SELF.get(ccat, 1) * damp
   elif ccat in PROTEIN and scat in PROTEIN: pen = 0.35 * damp
   elif ccat in DRINKS and scat in DRINKS: pen = 0.4 * damp
   else: pen = damp
   print(f"cats: {SEL}={scat} {CAND}={ccat}  categoryPenalty={pen}")

   # 4. rarity factor: robust z of the avg edge vs the CANDIDATE's own distribution
   s = sorted(sc for _, sc in d["p"][str(cid)])
   q = lambda f: s[int((len(s)-1)*f)]
   median, iqr = q(.5), q(.75) - q(.25)
   z = (edge - median) / max(iqr, 5)
   rarity = min(max(z, 0.25), 1.5)
   print(f"rarity: median={median} iqr={iqr} z={z:.2f} -> factor={rarity:.2f}")
   final = edge/100 * rarity * pen
   print(f"final = {edge/100:.2f} * {rarity:.2f} * {pen} = {final:.3f}  badge={round(min(final,1)*99)}")
   EOF
   ```

   Expected output shape (real run, 2026-07-11):
   ```
   raw edge lemon->honey: 41
   bases: lemon->lemon  honey->honey  suppressed=False
   cats: lemon=fruit honey=sweet  categoryPenalty=1
   rarity: median=12 iqr=10 z=2.90 -> factor=1.50
   final = 0.41 * 1.50 * 1 = 0.615  badge=61
   ```

   Caveats: this traces a SINGLE selected ingredient. For multi-selection, the average
   is `sum of covered edges / n` and the coverage gate applies. It also does not model
   the blended grid's diversity decay — a candidate can score high yet sit below
   grid position 9 because its category was already shown (check the swimlane view,
   which has no decay).
3. To see the engine's actual output (not a reimplementation), add a temporary
   `it.only` probe in `web/src/db.test.ts` using the existing `topN()` helper and run
   `npx vitest run src/db.test.ts` in `web/`. Delete the temporary probe afterwards.
4. In the live app, compare with and without `?ranking=raw` to isolate the rarity
   factor.

## Procedure B — change a knob or the formula

1. One branch per change (see the add-feature skill for workflow).
2. Make the change in `web/src/db.ts` only. Keep the explanatory comments honest —
   they are the institutional memory.
3. Run the probes: `npm test` in `web/`. Three outcomes:
   - All green → proceed.
   - A probe fails and the behaviour change was NOT intended → your change is a
     regression; fix the change, not the probe.
   - A probe fails and the change IS intended → update the probe **in the same
     commit** and explain the reasoning in the commit message. This is the probe-update
     protocol; probes encode owner-signed-off behaviour. NEVER delete a probe to make
     the suite pass (CLAUDE.md rule). Precedent: the cinnamon probe was consciously
     relaxed from "no spice in top-9" to "at most one other spice" when rarity (#45)
     landed — the relaxation and its reason live in the probe's comment.
4. Run the evaluation report if judgments exist (see Procedure C) and quote
   before/after metrics in the commit message.
5. Full gate before merging: `python3 pipeline/validate_pairings.py` (repo root),
   `npm test` and `npm run build` (both in `web/`) — same as CI
   (`.github/workflows/validate.yml`).

## Procedure C — the evaluation kit (issues #50 and #53)

Purpose: replace vibes-driven tuning with measured owner judgment.

- **Pool**: `web/public/eval/pool.json` — 25 probe ingredients, each with ~30–40
  pooled candidates (union of top-15 under several formula variants + random
  mid-rank; TREC-style pooling, generated by `pipeline/generate_eval_pool.py`).
  Each probe has `split: "dev" | "holdout"` — currently 18 dev / 7 holdout (count it,
  don't trust this).
- **Judgments**: the owner grades candidates in `web/public/annotate.html`
  (2 = "I'd love the app to suggest this", 1 = fine/expected, 0 = useless/wrong).
  Saves to `pipeline/eval/judgments.json` **on `main` via the GitHub Contents API**
  (token in localStorage `curate_gh_token`) — so the file may exist on `main` but not
  in your stale checkout: `git pull` before evaluating. Format:
  `{v, judgments: {probe: {candidate: 0|1|2}}, lastSaved}`.
- **Report**: `web/src/eval.test.ts`, runs inside `npm test`. Skips (`describe.skipIf`)
  until judgments.json exists with ≥ 200 total judgments (`MIN_JUDGMENTS`). Metrics
  per probe, averaged per split, printed to console:
  - `P@9` — fraction of judged top-9 with grade ≥ 1
  - `Discovery@9` — fraction of judged top-9 with grade == 2
  - `Recall@36` — fraction of the probe's grade-2 pairs found in top-36
  - `nDCG@9` — graded ranking quality over judged positions (the comparison scalar)
  It REPORTS, it does not gate. Issue #50 step 3 turns it into dev-split assertions
  once baseline + targets are agreed with the owner.
- **Discipline** (issue #50, non-negotiable): tuning only ever looks at the **dev**
  split. The **holdout** split is reported once per accepted change, never used to
  choose parameters. Baseline (current + raw formulas) is measured BEFORE targets are
  set.
- **Planned path** (issue #50's iteration plan; issue #53 is the owner saying
  annotation is done and asking for the evaluation): make the ranking constants in
  `db.ts` injectable, build a search harness that runs the REAL engine (no replica)
  across parameter grids, report dev+holdout metrics per config, owner approves the
  winner. Issue #53 also flags: the owner graded "uninteresting" as 0 (e.g. rice with
  anything), wants a consistency review of labels, and floated rating additions to
  combinations rather than 1-1 pairs — read #53 before acting on the metrics.

## Verification

- `npm test` in `web/`: expect `Test Files  1 passed | 1 skipped` (eval skipped while
  judgments are missing/below 200) or `2 passed`, and 0 failures.
- `python3 pipeline/validate_pairings.py` from repo root: expect final line
  `All consistency checks passed.`
- `npm run build` in `web/`: must complete (CI runs it too).
- For a tuning change: paste the eval report deltas (dev split) and the holdout
  numbers (once) into the commit message.

## Failure modes

| Symptom | Cause | Fix |
| --- | --- | --- |
| "ingredient not deployed: X" thrown by a test helper | name exists in base but was deleted/merged by curation | check `pipeline/curation.json` (deleted/merged); trace with the deployed JSON, not the base |
| Candidate has a strong raw edge but never appears | same-base suppression (#44) or category penalty + decay | run Procedure A stages 2–3; check taxonomy `b` chain in `web/public/taxonomy.json` |
| Suggestion list ignores your constant change in the browser | you're looking at `?ranking=raw`, or the SW served a stale bundle | remove the query param; hard-reload (see deploy-and-debug skill) |
| Rarity factor pinned at 0.25 or 1.5 for everything you test | that's the clamp working — z-scores are extreme for niche candidates | expected; compare against `?ranking=raw` before concluding it's broken |
| eval.test.ts silently skipped | `pipeline/eval/judgments.json` missing locally or < 200 judgments | `git pull` (annotate.html saves straight to main); check count: `python3 -c "import json; j=json.load(open('pipeline/eval/judgments.json'))['judgments']; print(sum(len(v) for v in j.values()))"` |
| Probe fails after a pure data change (curation edit) | probes run on deployed data; curation changes ranking inputs | legitimate — decide with the owner whether the data or the probe is right; see edit gates below |
| Scores > 1 or badge shows > 99 | a clamp was removed in stage 4 | restore `Math.min(..., 1)` in BOTH `getRecommendations` and `getRecommendationsByCategory`; the "scores stay within the badge range" probe guards this |
| Lane #1 disagrees with blended grid's first-of-category | `scoreCandidates` forked between the two views | un-fork; the "lane scores agree with the shared scoring stage" probe guards this |

## Hard rules

- **`scoreCandidates()` is shared by the blended grid and the swimlanes — never fork
  the formula between the two views.** WHY: a probe explicitly asserts lane tops match
  the blended ranking; a fork means the two views silently disagree about the same data.
- **Penalties and rarity NEVER apply to LOO/harmony scoring (`computeLooScores`).**
  WHY: penalties shape the *suggestion list*; LOO *measures compatibility* of what the
  user already chose — damping it would falsely flag their selections as clashing.
- **Never delete a probe to make the suite pass; update it in the same commit with
  reasoning.** WHY: probes are the owner's signed-off contract; deleting one erases
  the record of what was promised (CLAUDE.md).
- **Keep scores clamped ≤ 1; the badge is `round(score × 99)`.** WHY: rarity can push
  a score past 1; an unclamped score renders a nonsense badge (AUDIT §6 scar: FAQ
  labels vs badge math).
- **Never tune against the holdout split.** WHY: it's the only unbiased estimate of
  whether a tuning change generalises; touch it and issue #50's discipline is dead.
- **Never add a top-N cap to pair storage in `pairings.json`.** WHY: the TOP_N=50
  incident (AUDIT §3) would have silently truncated ~90% of edges for high-degree
  ingredients; the validator now detects cap signatures.
- Sibling skills: workflow/branching/merging → **add-feature**; stale data in the live
  app or SW weirdness → **deploy-and-debug**.

## When to STOP and ask the owner (txmnzia, samuelouden@gmail.com)

- Any change that flips a probe in `db.test.ts` and you are not certain the owner
  wants the new behaviour — probes are their sign-off.
- Setting eval baseline/targets, or shipping a grid-search winner (#50 requires owner
  approval of the winning config).
- Anything that changes `pairings.json` ingredient count or names, or any data file —
  destructive changes need confirmation before merging (CLAUDE.md).
