---
name: deploy-and-debug
description: The flavour-pairing deploy pipeline (GitHub Pages via deploy.yml), the PWA service worker, and debugging the live app. Use when "the live app shows stale/wrong data", a deploy failed, PWA/offline behaviour is weird, a curation or annotation save isn't appearing in the app, a standalone tool page serves the app shell, or a rollback is requested.
---

# Deploy pipeline, service worker, and live-app debugging

Live app: GitHub Pages, base path `/flavour-pairing/`. There is **no backend and no
state outside git** — everything the live app shows is a function of the `main` branch
at the last successful deploy, plus the visitor's service-worker cache.

## Before you start

1. Read `.github/workflows/deploy.yml` (short) and the `VitePWA` block in
   `web/vite.config.ts`.
2. Understand the one distinction that explains most confusion:
   - `web/public/pairings.json` (committed) = the BASE, ~3,517 ingredients.
   - The DEPLOYED pairings.json = base with `pipeline/curation.json` applied **on the
     CI runner at build time**, ~1,038 ingredients (drifts — derive it, don't trust
     this). The deployed file is **never committed anywhere**.
3. For background on data files, `pipeline/DATA.md` is authoritative.

## How a deploy works (`.github/workflows/deploy.yml`)

Triggers: `push` to `main`, and `workflow_dispatch` (manual).

Steps, in order (job `build`, then `deploy`):
1. `actions/checkout` (fetch-depth 0).
2. **`python pipeline/apply_curation_json.py`** — no arguments; defaults rewrite
   `web/public/pairings.json` IN PLACE **on the runner only** (resolves merge chains,
   delete-wins precedence, applies `badPairs`, renumbers indices, fixes
   `meta.ingredients`). Prints e.g.
   `Curation applied: 909 deleted, 1570 merged, 0 pair edges removed → 1038 ingredients remain`
   (real output 2026-07-11; every number drifts as curation continues — note the
   deleted/merged counts differ from curation.json's raw counts because chain
   resolution reclassifies some merges as deletes).
3. `actions/setup-node` (Node 20) → `npm install` in `web/`.
4. `npm run build` in `web/` = `tsc -b && vite build` → `web/dist/` (includes the
   generated service worker).
5. Upload `web/dist` → `actions/deploy-pages`. Concurrency group `pages`, one deploy
   at a time, in-progress runs cancelled.

Also on every push to `main`: `.github/workflows/validate.yml` (structural validator +
ranking probes + build). It validates but does not gate the deploy — the two workflows
run independently.

**What triggers a deploy in practice:**
- Any `git push` to `main`.
- A save from the curation/annotation UIs (`curate.html`, `merge.html`,
  `annotate.html`): these PUT real commits to `main` via the GitHub Contents API
  using the owner's PAT (localStorage `curate_gh_token`), targeting
  `pipeline/curation.json` or `pipeline/eval/judgments.json`. **API commits made with
  a PAT count as pushes and trigger `on: push` workflows**, so a UI save does deploy
  automatically. (Only commits made with a workflow's own `GITHUB_TOKEN` skip
  triggering — that case doesn't exist here.) Confirm in the Actions tab rather than
  assuming: `gh run list --workflow deploy.yml --limit 5` or the GitHub UI.
- `workflow_dispatch` is the manual fallback: re-run a failed deploy, or force a
  rebuild without a new commit (the deploy.yml comment cites "after editing
  curation.json out-of-band").

## Service worker behaviour (`web/vite.config.ts`, vite-plugin-pwa)

- `registerType: "autoUpdate"` — new SW activates on next visit, no prompt.
- **`pairings.json` is `NetworkFirst`** (cache `pairings-data`, 7-day expiry, 5 s
  network timeout): a reload WITH network gets fresh data immediately; the cache is
  only a fallback for offline/slow. Data staleness is therefore rarely the SW's fault.
- **The app shell (js/css/html) is precached** (`globPatterns`). After a deploy, the
  first visit downloads the new SW in the background and serves the OLD shell; the
  NEW shell appears on the SECOND visit (or after closing all tabs / "Update on
  reload" in DevTools). So: fresh data + old UI for one visit is NORMAL.
- **`includeAssets: ["pairings.json", …]` is misleading — it does NOT precache the
  data** (AUDIT notes: precache is ~326 KB; the ~1.5 MB JSON goes through the
  NetworkFirst runtime cache). Offline works only after the first data fetch. Don't
  "fix" this by precaching the data.
- Standalone tools are excluded twice: `globIgnores` and `navigateFallbackDenylist`
  (`curate.html`, `merge.html`, `annotate.html`, `attributions.html`). A new tool
  missing from the denylist gets swallowed by the SW, which serves the React shell
  instead — see add-feature.
- Ingredient images: `manifest.json` StaleWhileRevalidate, `.webp` tiles CacheFirst
  (90 days).
- `recipes.json` **404s on every load by design** — no recipe catalog is deployed
  (dormant feature, issue #5). `loadDatabase()` in `web/src/db.ts` uses
  `Promise.allSettled` and degrades gracefully. A `recipes.json` 404 in the console
  is NOT a bug; do not "fix" it.

## Procedure — "the live app shows wrong/stale data"

Work the checklist in order; stop at the first hit.

1. **Did the deploy run and go green?** Check the Actions tab (or
   `gh run list --workflow deploy.yml --limit 5`). Red build → read the log; the
   usual culprits are `apply_curation_json.py` failing on a bad curation edit, `tsc`
   errors, or a failing `npm install`. No run at all → nothing was pushed to `main`;
   a UI save may have failed silently (check the tool's status line / token).
2. **Is the change in curation or in the base?** A curation edit changes the deployed
   data only; the committed `web/public/pairings.json` is untouched. Confirm the edit
   is actually on `main`: `git fetch && git show origin/main:pipeline/curation.json | head`.
3. **Reload semantics.** Data (`pairings.json`) is NetworkFirst — one normal reload
   with network refreshes it. Shell changes need a second visit (or DevTools →
   Application → Service Workers → "Update on reload" → hard reload). If in doubt,
   test in a private window: no SW, no cache.
4. **Reproduce the deployed data locally and check your expectation against it:**
   ```bash
   # repo root — runs the REAL deploy transform on a copy, validates it, keeps it
   python3 pipeline/validate_pairings.py --deployed-out /tmp/deployed.json
   python3 - <<'EOF'
   import json
   d = json.load(open("/tmp/deployed.json"))
   print(len(d["i"]), "ingredients deployed")
   print("your ingredient:", [n for n in d["i"] if "lemon" in n])
   EOF
   ```
   If the ingredient/edge is wrong HERE, it's a data problem (curation or base), not
   a deploy problem → **edit-pairing-data** skill.
5. **Ranking looks wrong rather than data missing?** Load the live app with
   `?ranking=raw` to disable the rarity debias and isolate its effect; then follow
   the **tune-ranking** debugging recipe.

## Procedure — rollback

Nothing holds state except git, so rollback = revert the offending commit on `main`:

```bash
git checkout main && git pull
git revert <bad-commit-sha>       # produces a new commit; never force-push main
git push                          # push to main triggers a fresh deploy
```

For a bad curation-UI save, revert the API commit the same way (its message is e.g.
"Update ranking evaluation judgments" or the curate/merge save message). If a deploy
succeeded from a state you can't revert cleanly, fix forward and push — the next
deploy fully replaces the previous one.

## Local dev vs prod — expected differences

- `npm run dev` in `web/` serves the **COMMITTED base without curation applied**:
  ~3,517 ingredients, including everything the owner deleted or merged. Suggestion
  lists and counts differing from prod is EXPECTED, not a bug.
- To run the app on prod-equivalent data locally: derive it, temporarily overwrite,
  and restore afterwards:
  ```bash
  python3 pipeline/validate_pairings.py --deployed-out /tmp/deployed.json
  cp /tmp/deployed.json web/public/pairings.json     # TEMPORARY — do not commit
  # … npm run dev, inspect …
  git checkout -- web/public/pairings.json           # restore the base
  ```
  The tests already do this properly: `npm test` builds `web/test/.deployed.json`
  and probes against it.
- The dev server does not register the service worker the way prod does; SW bugs must
  be reproduced against a build (`npm run build && npm run preview` in `web/`) or the
  live site.

## Verification

- Deploy health: Actions tab shows both "Deploy to GitHub Pages" and
  "Data & ranking consistency" green for the head commit of `main`.
- Deployed data sanity, locally: `python3 pipeline/validate_pairings.py` ends with
  `All consistency checks passed.` and prints the current deployed count
  (`deployed: NNNN ingredients` — the ~1,038 figure drifts with curation).
- In the browser: footer shows the deployed ingredient count; DevTools → Network
  confirms `pairings.json` fetched from network (NetworkFirst) on reload.

## Failure modes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Curation edit saved in UI but live app unchanged | save failed (bad/expired token), or deploy still running/failed | check tool status + Actions tab; re-save or `workflow_dispatch` deploy.yml |
| Live app shows OLD interface after a deploy | app shell is precached; new shell arrives on second visit | visit twice / hard reload with "Update on reload"; normal behaviour |
| Live app shows OLD data | rarely the SW (data is NetworkFirst); usually the deploy didn't run or the edit isn't on main | checklist steps 1–2 |
| curate/merge/annotate/attributions URL renders the main app | tool missing from `navigateFallbackDenylist` in `web/vite.config.ts` | add regex + `globIgnores` entry, rebuild, deploy (see add-feature) |
| Console 404 for `recipes.json` | by design — dormant feature #5, handled by `Promise.allSettled` | ignore; not a bug |
| Deploy red at "Apply curation decisions" | malformed `pipeline/curation.json` (bad JSON, merge cycle) | `python3 pipeline/validate_pairings.py` locally pinpoints it; fix or revert the curation commit |
| Deploy red at Build | `tsc` type error or dependency issue | reproduce with `npm run build` in `web/`; dev server not typechecking is why it "worked locally" |
| Deploy green but validate.yml red | data/probe inconsistency slipped in (deploy doesn't gate on validation) | treat as an incident: fix or revert immediately — the broken state is LIVE |
| App shows "Demo data" / tiny ingredient count | `pairings.json` failed to load or a truncated file was deployed | check Network tab + Actions log for the apply-curation step output |
| Offline mode empty on first ever visit | data is not precached (includeAssets is misleading) | expected: offline works only after the first successful data fetch |

## Hard rules

- **Never commit a curated/deployed `pairings.json` over the base.** WHY: the base
  (~3,517 ingredients) is the owned canonical database; the deployed file is a build
  artifact derived on the runner. Committing it destroys the ability to re-curate.
  If `git status` shows `web/public/pairings.json` modified after local
  experimentation, `git checkout -- web/public/pairings.json`.
- **Never commit `web/dist/` or `web/public/pairings.db`.** WHY: build artifacts;
  2.9 MB of them were once committed dead weight (AUDIT §10).
- **Never force-push or reset `main` to roll back — use `git revert`.** WHY: Pages
  deploys from main's head; API-created curation commits may sit above the commit
  you're removing, and history rewrites lose them.
- **Don't "fix" the recipes.json 404 or precache pairings.json.** WHY: both are
  deliberate (dormant feature #5; 1.5 MB precache would bloat every install — AUDIT
  accepted-behaviour notes).
- Sibling skills: what to change and how to branch/merge → **add-feature**; wrong
  suggestions with correct data → **tune-ranking**; wrong deployed ingredients/edges
  → **edit-pairing-data**.

## When to STOP and ask the owner (txmnzia, samuelouden@gmail.com)

- Before reverting any commit that contains the owner's own curation or annotation
  saves (their manual grading/curation work would be undone — coordinate first).
- Before any rollback that changes the deployed ingredient list beyond restoring the
  previous known-good state.
- If a deploy is red because of a data-file problem you'd have to edit data files to
  fix — data changes need owner confirmation (CLAUDE.md).
