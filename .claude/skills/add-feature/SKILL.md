---
name: add-feature
description: Implement a feature or fix in the flavour-pairing app to this project's standard — backlog workflow, branch/merge policy, codebase orientation, i18n and service-worker conventions, and the definition of done. Use when implementing a GitHub issue, when asked to "add/change/build X in the app", when the owner lists feature ideas (each becomes a GitHub issue), or at the start of any coding session in this repo.
---

# Add a feature or fix

Repo: `txmnzia/flavour-pairing`. Static React PWA in `web/`, Python 3 stdlib pipeline
in `pipeline/`, deployed to GitHub Pages on every push to `main`. No backend.

## Before you start

1. Read `CLAUDE.md` (repo root) — it is the contract and overrides defaults.
2. If the task touches data files (`web/public/pairings.json`,
   `pipeline/curation.json`, `pipeline/merges.json`, `web/public/taxonomy.json`),
   read `pipeline/DATA.md` first and use the **edit-pairing-data** skill. If it
   touches ranking in `web/src/db.ts`, use the **tune-ranking** skill.
3. Check the backlog: list open issues on `txmnzia/flavour-pairing` (gh CLI or GitHub
   MCP tools, whichever the session has). **Only implement the highest-priority open
   issue. Never work ahead.**
4. Confirm you are not on `main`: `git branch --show-current`. Every feature or fix
   gets its own branch — never implement on `main` directly.

## The backlog workflow (from CLAUDE.md — follow exactly)

- **Owner lists feature ideas** → create ONE GitHub issue per idea in
  `txmnzia/flavour-pairing`, each with: a clear problem description, the options
  considered, and a recommended approach. Do not start implementing.
- **Implementing** → pick only the highest-priority open issue. One branch per issue;
  keep the branch clean and focused (branches exist for easy rollback).
- **When the change is complete** (definition of done below) → **merge to `main` and
  push immediately — do not wait for permission, do not ask.** This applies to
  features, bug fixes, and copy changes alike.
- **Exception — destructive changes**: schema changes, removing features, ANY change
  to data files → confirm with the owner before merging.

## Codebase tour (orientation)

- `web/src/App.tsx` — all app state (selection, lanes, language, query, FAQ modal).
  Flow: `loadDatabase()` → `getAllIngredients()`; on selection change →
  `getRecommendationsByCategory` (swimlanes, LANE_N=12), `getRecipesForIngredients`,
  `computeLooScores`. Browse list (no selection) sorts by `freq` with
  trimmed-query prefix ranking.
- `web/src/db.ts` — **the only data-access layer**. All fetching of
  `pairings.json` / `recipes.json` / `taxonomy.json` and all scoring lives here.
  Components never touch raw data.
- `web/src/components/` — `SearchInput.tsx`, `RecommendationList.tsx` (cards, score
  badges, LOO outlier highlighting, lanes), `IngredientTile.tsx`,
  `IngredientChip.tsx`, `FAQ.tsx`.
- `web/src/types.ts` — `Ingredient`, `Pairing`, `CategoryLane`, `DbStatus`.
- `web/src/utils/` — `translateFr.ts` (ingredient-name FR translation),
  `categoryLabels.ts` (EN/FR lane headers), `format.ts`, `ingredientEmoji.ts`,
  `ingredientImage.ts` (slug must match `slugify()` in `pipeline/fetch_images.py`).
- `web/public/*.html` — standalone vanilla-JS tools (curate, merge, annotate,
  attributions), outside the React bundle, saving to `main` via GitHub Contents API.
- Tests: `web/src/db.test.ts` (owner-signed-off ranking probes),
  `web/src/eval.test.ts` (metrics report). Both run on DEPLOYED data built by
  `web/test/global-setup.ts` (needs `python3` on PATH).
- CI: `.github/workflows/validate.yml` (validator + tests + build; triggers: push to
  `main`, all pull requests, manual dispatch — note a plain push to a feature branch
  without a PR does NOT run CI, so run the gate locally),
  `.github/workflows/deploy.yml` (Pages deploy — see deploy-and-debug skill).

## Project conventions — each has a scar story

1. **New standalone HTML tool ⇒ update `web/vite.config.ts`.** Add it to BOTH
   `workbox.globIgnores` and `workbox.navigateFallbackDenylist` (current entries:
   `curate.html`, `merge.html`, `annotate.html`, `attributions.html`;
   `globIgnores` additionally lists `ingredient-images/**`, which is not a
   tool — leave it alone). WHY: the PWA
   service worker's navigate fallback otherwise swallows the URL and serves the React
   app shell instead of your tool — it "works locally, 404-ish in prod".
2. **No hardcoded user-facing strings — every UI string is localized EN/FR** (AUDIT
   §5 scar: `SearchInput` once showed the French "Chargement…" to English users, and
   `RecommendationList` showed English-only strings in French mode). Pattern used
   everywhere: `lang === "fr" ? "…" : "…"` driven by the `lang` state in `App.tsx`,
   passed down as a prop.
3. **UI-string translation ≠ ingredient-name translation.** UI strings use the
   `lang` ternaries above. Ingredient NAMES go through `translateFr()`
   (`web/src/utils/translateFr.ts`: dict lookup + prefix/colour/suffix heuristics).
   Never route a UI string through the ingredient translator — AUDIT §5: empty-state
   messages were once fed to it and could never translate.
4. **French dictionaries are duplicated on purpose — keep all copies in sync**:
   - `web/src/utils/translateFr.ts` heuristics + `web/src/translations/fr.json`
     (bundled dict, ~3,653 entries, written by `pipeline/generate_translations.py`);
   - `web/public/translations/fr.json` (identical copy, fetched at runtime by
     `annotate.html`);
   - inline `frDict` in `web/public/curate.html` (~line 268).
   A name added/renamed in one must land in all (CLAUDE.md rule).
5. **Trim search queries consistently** (AUDIT §7 scar: filtering used the trimmed
   query but prefix-ranking used the raw one, so `"tom "` matched tomato without
   ranking it first). In `App.tsx` both use `query.toLowerCase().trim()` — keep it
   that way in any new search code.
6. **Ingredient names are the runtime join key** across `pairings.json`,
   `recipes.json`, `taxonomy.json`, translations, curation, and image slugs. A rename
   in one requires the same rename in all — see edit-pairing-data.
7. **Git hygiene**: never commit `web/public/pairings.db` (generated; was once 2.2 MB
   of committed dead weight, AUDIT §10) or `web/dist/` (gitignored build output).
   DO commit `web/package-lock.json` and keep it current. Commit and push after every
   working change.
8. **Curation-UI code** (if you touch `curate.html`/`merge.html`/`annotate.html`):
   decode GitHub API content with `TextDecoder`, never bare `atob()` (AUDIT §4
   mojibake); merges must go through the shared `recordMerge` discipline — resolve
   target through existing merges, re-point earlier merges, refuse
   self-merges/cycles/deleted targets (AUDIT §§1–2: merge chains silently destroyed
   pairing edges at deploy).

## Procedure

1. Pick the highest-priority open issue (ask the owner if priority is ambiguous).
2. `git checkout main && git pull`, then `git checkout -b <short-issue-slug>`.
3. Implement, following the conventions above. Keep the diff focused on the one issue.
4. If behaviour covered by a probe in `web/src/db.test.ts` changes intentionally,
   update the probe in the same commit with reasoning in the commit message (never
   delete a probe) — full protocol in **tune-ranking**.
5. Run the full gate (Verification below). Fix until green.
6. Commit with a message that references the issue (e.g. `Fix …, closes #NN`), push
   the branch.
7. Merge to `main` and push immediately (no permission needed) — UNLESS the change is
   destructive (schema/data/feature-removal): then stop and confirm with the owner
   first.
8. Verify the deploy went green (see **deploy-and-debug**) and close the issue if the
   commit message didn't auto-close it.

## Verification — definition of done (same as CI validate.yml)

Run all three; all must pass before merging anything touching data, pipeline, or
`web/src/db.ts` — and they're cheap enough to run for every change:

```bash
# repo root
python3 pipeline/validate_pairings.py     # expect: "All consistency checks passed."

cd web
npm test                                  # vitest; expect 0 failures
                                          # (eval suite may show "skipped" — normal
                                          #  while judgments < 200)
npm run build                             # tsc -b && vite build; must complete
```

Plus: changed UI? Check BOTH languages (toggle EN/FR in the header). New HTML tool?
Confirm the vite.config.ts denylist entry exists.

## Failure modes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `npm test` fails in `global-setup.ts` | `python3` not on PATH (test setup shells out to apply curation) | install/expose python3; it's the same dependency the deploy workflow has |
| A ranking probe fails after your UI-only change | you touched data flow or db.ts indirectly | see tune-ranking probe-update protocol; never delete the probe |
| New tool page loads the main app instead of the tool | missing `navigateFallbackDenylist` entry in `web/vite.config.ts` | add regex + `globIgnores` entry, rebuild |
| French mode shows English text (or vice versa) | hardcoded string, or UI string routed through `translateFr` | localize via `lang` prop pattern (AUDIT §5) |
| `tsc -b` fails but dev server worked | vite dev doesn't typecheck | fix types; CI runs `npm run build` |
| CI didn't run on your branch push | validate.yml only triggers on push to `main`, PRs, and dispatch | open a PR, or rely on the local gate before merging |
| Accidentally committed `pairings.db` or `dist/` | generated artifacts | `git rm --cached` them; they're gitignored for a reason (AUDIT §10) |

## Hard rules

- **Never implement on `main`; one branch per issue.** WHY: branches are the rollback
  mechanism — `git revert`/branch deletion keeps incidents cheap.
- **Never work ahead of the highest-priority open issue.** WHY: the owner prioritises;
  speculative work has been thrown away before and pollutes the backlog.
- **Merge + push immediately when done — except destructive/data changes, which need
  owner confirmation first.** WHY: CLAUDE.md policy; the owner reviews live, not via
  PR queues — but destroyed data cannot be un-deployed by review.
- **Never regenerate or truncate `web/public/pairings.json`; never add a top-N cap.**
  WHY: AUDIT §3 — a TOP_N=50 cap would have silently dropped ~90% of edges for
  high-degree ingredients. Any ingredient count/name change needs explicit owner
  sign-off.
- **Never resurrect the v1 `"cuisineIdx,idx"` key format.** WHY: AUDIT §11 — a legacy
  workflow that regenerated v1 format was a loaded footgun and was deleted; `p` keys
  stay plain string indices (`"0"`, `"251"`). Future per-cuisine overlays (#47) are
  separate `pairings.<cc>.json` files, same schema.
- Sibling skills: ranking changes → **tune-ranking**; data edits →
  **edit-pairing-data**; anything about deploys, the service worker, or the live app
  misbehaving → **deploy-and-debug**.

## When to STOP and ask the owner (txmnzia, samuelouden@gmail.com)

- Before merging any destructive change: schema changes, feature removal, ANY change
  to data files (`pairings.json`, `curation.json`, `merges.json`, `taxonomy.json`).
- Any change to `pairings.json` ingredient count or names — explicit sign-off required.
- When issue priority is unclear, or a new idea seems more urgent than the backlog
  order — file the issue, then ask; don't self-prioritise.
