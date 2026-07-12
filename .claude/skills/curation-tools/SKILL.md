---
name: curation-tools
description: Maintain, debug, and extend the standalone HTML curation tools (web/public/curate.html, merge.html, annotate.html) and their GitHub-API save flow. Use when fixing or extending any curation UI, adding a new standalone HTML tool to web/public/, debugging GitHub token or save problems ("my curation decisions aren't saving/syncing", red sync dot, "Save failed"), when merge decisions look wrong or chained, or when a tool page loads the main app instead of itself.
---

# Curation tools — the standalone HTML pages

Three self-contained vanilla-JS pages live in `web/public/` and are served
next to the React app on GitHub Pages (e.g.
`https://txmnzia.github.io/flavour-pairing/curate.html`):

| Tool | Purpose | Writes (via GitHub API, on `main`) |
|------|---------|-------------------------------------|
| `web/public/curate.html` | Swipe-card review: keep / delete / merge one ingredient at a time | `pipeline/curation.json` |
| `web/public/merge.html` | Batch merge: groups variants by shared key terms, pick a canonical (👑) + duplicates | `pipeline/curation.json` |
| `web/public/annotate.html` | Grade pooled pairing suggestions 0/1/2 for the ranking evaluation (issue #50) | `pipeline/eval/judgments.json` |

Key architecture facts (all verified against source):

- **No build step.** Plain HTML + inline `<script>` vanilla JS. Vite copies
  `web/public/` verbatim into `web/dist/`. There is no TypeScript, no imports,
  no bundling — edit the file, reload the page.
- **Excluded from the service worker.** `web/vite.config.ts` lists them in
  `navigateFallbackDenylist: [/\/curate\.html$/, /\/merge\.html$/, /\/annotate\.html$/, /\/attributions\.html$/]`
  and in `workbox.globIgnores`. Without the denylist entry the PWA service
  worker swallows the navigation and serves the app shell instead of the tool.
- **No backend.** The tools talk directly to the GitHub Contents API from the
  browser, authenticated with a personal access token stored in
  `localStorage`.
- **The tools write only `pipeline/curation.json` (curate/merge) and
  `pipeline/eval/judgments.json` (annotate). They never modify
  `pairings.json`** (DATA.md invariant 4). Curation is applied at deploy time
  by `pipeline/apply_curation_json.py`.

## Before you start

1. Read `pipeline/DATA.md` (sections "pipeline/curation.json", "Curation UIs",
   "Invariants") and `AUDIT.md` items 1, 2, 4 — they are the scar stories
   behind every hard rule below.
2. Know the exact constants (from the `<script>` headers of the tools):
   - `REPO = 'txmnzia/flavour-pairing'`
   - curate.html / merge.html: `CFILE = 'pipeline/curation.json'`, `CBRANCH = 'main'`
   - annotate.html: `JFILE = 'pipeline/eval/judgments.json'`, `BRANCH = 'main'`
   - localStorage keys:
     - `curate_gh_token` — the GitHub token, **shared by all three tools**
       (needs `contents: write` on the repo; fine-grained token scoped to this
       one repo is preferred — AUDIT notes: token in localStorage on a static
       site is acceptable for a personal tool, never use a broadly-scoped one)
     - `curate_decisions` — local cache of curation decisions, **shared by
       curate.html and merge.html** (constant is named `LS_DECISIONS` in
       curate.html and `LS_DEC` in merge.html — same string value)
     - `eval_judgments` — local cache of grades, annotate.html only (`LS_J`)
3. After ANY change to curation data or tool logic, the consistency tests must
   pass before merging: `python3 pipeline/validate_pairings.py` (repo root)
   and `npm test` (in `web/`). CI enforces both.

## The GitHub save/load flow (as implemented — copy this pattern exactly)

All three tools use the same `ghFetch` helper:

```js
fetch('https://api.github.com' + path, { ...opts, headers: {
  'Authorization': 'Bearer ' + token,
  'Accept': 'application/vnd.github+json',
  'X-GitHub-Api-Version': '2022-11-28',
  ...(opts.headers || {}) } })
```

**Load** (`loadFromGH`):
1. `GET /repos/txmnzia/flavour-pairing/contents/pipeline/curation.json?ref=main`
2. Decode `meta.content` **as UTF-8** — never bare `atob()`:
   ```js
   const bytes = Uint8Array.from(atob(meta.content.replace(/\n/g, '')), c => c.charCodeAt(0));
   const remote = JSON.parse(new TextDecoder().decode(bytes));
   ```
3. Merge remote with the local `curate_decisions` cache:
   - `validated` and `deleted`: **set union** of local and remote
   - `merged`: `{ ...remote.merged, ...local.merged }` — local unsaved merges win
   - **Spread `...remote` first** when rebuilding the decisions object, so
     fields the UI does not manage (`badPairs`, anything unknown) survive.
4. Write the merged result back to localStorage.

**Save** (`saveToGH`):
1. `GET` the file again to grab the current `sha` and re-read remote content
   (`remoteExtra`) so unmanaged fields are preserved.
2. Build `payload = { ...remoteExtra, ...decisions, lastSaved: new Date().toISOString() }`.
   Note: at save time the managed keys (`validated`/`deleted`/`merged`) are
   **overwritten wholesale** by the local decisions — remote/local merging
   happens at load time, not save time.
3. `PUT` with body:
   ```js
   { message: 'Update curation decisions',
     content: btoa(unescape(encodeURIComponent(JSON.stringify(payload, null, 2)))),
     branch: 'main',
     sha }          // omitted only when the file does not exist yet
   ```
4. Saves are debounced: `scheduleAutoSave()` fires 20 s after the last action,
   plus an automatic save when the review queue completes. Sync dot:
   green = saved, amber = saving, red = failed.

**Semantics: last-writer-wins across devices.** This is an accepted risk
(AUDIT "Notes"): the SHA read→PUT is not a transaction, and save overwrites
the managed keys. Because `validated`/`deleted` are unioned on load, real data
loss requires two devices merging/deleting concurrently — acceptable for a
single-owner tool. Do not "fix" this with locking; do preserve the
load-time-union behaviour.

**annotate.html differs**: it merges at **save time too** — remote judgments
are folded in per (probe, candidate) with local winning, so parallel
annotation sessions never lose grades. Its commit message is
`'Update ranking evaluation judgments'`. Its data shape is
`{ v: 1, judgments: { [probe]: { [candidate]: 0|1|2 } }, lastSaved }`.
Grades: 0 = useless/wrong, 1 = fine but unexciting, 2 = interesting/love it.
The file feeds `web/src/eval.test.ts`, which skips below
`MIN_JUDGMENTS = 200` and reports (does not gate) metrics — issue #50.
annotate.html reads its candidate pool from `web/public/eval/pool.json`
(generated by `pipeline/generate_eval_pool.py`) and its French names from
`web/public/translations/fr.json` at runtime.
`pipeline/eval/judgments.json` does not exist until the first save creates it
("File not on GitHub yet — save to create it" is normal on first use).

## Merge integrity — recordMerge (never bypass it)

Scar story (AUDIT §§1–2): the UIs once allowed merging into already-merged-away
ghosts and left earlier merges orphaned. Result: **126 merge chains**
(`beef bouillon → beef broth → beef`) whose edges were silently destroyed at
deploy time. `apply_curation_json.py` now resolves chains defensively, but the
UIs must never create them.

Both curate.html and merge.html carry this helper with identical merge logic
(curate.html's copy additionally calls `saveDecisionsToLS(); scheduleAutoSave();`
just before `return true;` — that persistence tail is the only difference).
Any new merge path MUST go through it (or a copy with the same logic).
This is merge.html's version:

```js
// Record a merge without ever creating a chain: resolve the target through
// existing merges, and re-point earlier merges into `from` at the new target.
function recordMerge(from, to) {
  let target = to;
  const seen = new Set([from]);
  while (mergedMap.has(target) && !seen.has(target)) {
    seen.add(target);
    target = mergedMap.get(target);
  }
  if (target === from || deletedSet.has(target)) return false;
  decisions.merged[from] = target;
  mergedMap.set(from, target);
  for (const [src, dst] of mergedMap) {
    if (dst === from) {
      decisions.merged[src] = target;
      mergedMap.set(src, target);
    }
  }
  return true;
}
```

What it guarantees, in order:
1. Resolves `to` through existing merges to the final target (cycle-safe via
   `seen`).
2. Refuses self-merges (`target === from`) and merges into deleted targets.
3. Re-points every earlier merge that targeted `from` at the new target, so no
   source is left pointing at a name that is now merged away.

Equally important: **candidate lists must never offer merged-away or deleted
names.** curate.html's `filterM()` and `getSuggestions()` and merge.html's
`activeMembers()` all filter with
`!deletedSet.has(name) && !mergedMap.has(name)`. Keep that filter on any new
picker you add.

## Fields the UIs preserve but must never edit

`pipeline/curation.json` contains `badPairs` (issue #46, hand-maintained edge
removals) and may gain other fields. The UIs keep them alive purely through
the spread order (`{ ...remote, ...managedKeys }` on load,
`{ ...remoteExtra, ...decisions }` on save). If you restructure the
save/load code, re-verify with a round-trip test that `badPairs` survives.
No UI ever writes to `badPairs`.

## French translation sync (frDict)

- curate.html has an **inline `frDict`** plus inline `PREFIX_FR` / `COLOR_FR` /
  `SUFFIXES` rules that mirror `web/src/utils/translateFr.ts` (which imports
  `web/src/translations/fr.json`). **Any translation added to one must be
  added to the other** (CLAUDE.md rule).
- merge.html has no French dict (EN only). annotate.html fetches
  `web/public/translations/fr.json` at runtime instead of inlining.
- So there are up to three places a new ingredient translation can be needed:
  `web/src/translations/fr.json`, `web/public/translations/fr.json`, and the
  inline `frDict` in curate.html.

## Procedure: fix or extend an existing tool

1. Create a branch (never work on `main` directly).
2. Edit the HTML file in `web/public/` directly — no build step.
3. Test locally: `cd web && npm run dev`, open
   `http://localhost:5173/flavour-pairing/curate.html` (base path is
   `/flavour-pairing/`). The tool fetches `./pairings.json` relative to
   itself, which the dev server serves from `web/public/`.
4. To test GitHub sync without touching real data, either skip connecting a
   token (all decisions stay in localStorage) or temporarily point `CFILE` at
   a scratch path — and revert before committing.
5. If you touched merge logic, keep `recordMerge`'s merge logic identical in
   curate.html and merge.html (it is duplicated by design — no shared module
   exists for build-less pages). The copies are NOT byte-identical today:
   curate.html's tail also calls `saveDecisionsToLS(); scheduleAutoSave();` —
   preserve that difference, but any change to the resolution/guard logic goes
   in both files in the same commit.
6. Run Verification below; commit; merge to `main` and push (CLAUDE.md
   workflow) — the deploy workflow republishes the tool automatically.

## Procedure: add a NEW standalone HTML tool

1. Create `web/public/<tool>.html` — copy the skeleton of the closest existing
   tool (annotate.html is the smallest). Keep it fully self-contained: inline
   CSS + JS, no imports.
2. Reuse the existing patterns verbatim: `ghFetch`, the TextDecoder decode,
   the SHA read → spread-remote-first → PUT save, the `curate_gh_token`
   localStorage key, the 20 s `scheduleAutoSave`, the sync dot.
3. **Add it to the service worker exclusions in `web/vite.config.ts`** — both
   lists:
   - `workbox.globIgnores`: add `"<tool>.html"`
   - `workbox.navigateFallbackDenylist`: add `/\/<tool>\.html$/`
   Skipping this is the classic failure: the deployed URL renders the React
   app shell instead of your tool.
4. Document the tool in `pipeline/DATA.md` (Curation UIs section) and in
   `CLAUDE.md`'s Curation UIs list.
5. If it writes a new file, decide the path under `pipeline/` and give it a
   distinct localStorage cache key (pattern: annotate.html uses
   `eval_judgments`).
6. Run Verification below.

## Verification

Run all of these before merging:

```bash
# 1. Data + curation structural validation (repo root)
python3 pipeline/validate_pairings.py
# expect: exits 0, "OK"-style summary, no cap-signature or chain errors

# 2. Ranking behaviour probes (needs python3 on PATH for global-setup)
cd web && npm test

# 3. Build — proves the SW config is still valid and the tool ships
npm run build   # in web/
ls dist/<tool>.html                             # tool copied to dist
grep -c '<tool>\.html' dist/sw.js || true       # must NOT appear in the precache manifest
```

For save-flow changes, do a manual round-trip against real GitHub: connect
token → make one trivial decision → Save ↑ → verify the commit on `main`
touches only the expected file → Load from GitHub on a second
browser/incognito profile → confirm the decision appears and `badPairs` is
still present in the committed JSON. **The trivial decision must be a KEEP
(a `validated` entry — record-only, zero deploy effect), never a test
delete or merge**: the save is a real commit to `main`, it triggers a real
GitHub Pages deploy, and a delete/merge would change the live ingredient
list without owner sign-off.

```bash
python3 -c "import json; d=json.load(open('pipeline/curation.json')); print(sorted(d.keys()))"
# expect: ['badPairs', 'deleted', 'lastSaved', 'merged', 'validated']
```

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| "My decisions aren't saving/syncing" / grey sync dot | No token connected on this device (`curate_gh_token` is per-browser localStorage) | ⚙ Settings → paste token → Connect. Decisions made while offline are in `curate_decisions` and sync on next save. |
| Red sync dot, "Save failed: Bad credentials" | Token expired/revoked | Generate a new fine-grained PAT with `contents: write` on txmnzia/flavour-pairing, reconnect. |
| Save failed with 409 / "does not match" | SHA went stale — another device or the deploy touched the file between GET and PUT | Load from GitHub (unions your local state in), then Save again. |
| `Ã©`-style mojibake in curation.json | Someone reintroduced bare `atob()` decoding | Restore the `Uint8Array` + `TextDecoder` decode (AUDIT §4). Repair the file from git history. |
| Merge target has no pairings in the deployed app / edges vanished | A merge chain was created by bypassing `recordMerge` | `apply_curation_json.py` resolves chains defensively, but fix the UI path; run `python3 pipeline/validate_pairings.py` (it checks curation for self-merges/cycles). |
| Tool URL shows the main app instead of the tool | Missing `navigateFallbackDenylist` entry in `web/vite.config.ts`, or a stale SW | Add the regex + globIgnores entry, rebuild, then hard-reload / unregister the service worker in DevTools. |
| `badPairs` disappeared from curation.json | Save path stopped spreading `remoteExtra` first | Restore spread order; recover `badPairs` from git history of `pipeline/curation.json`. |
| annotate.html: "pool.json missing — run pipeline/generate_eval_pool.py" | `web/public/eval/pool.json` absent | Run `python3 pipeline/generate_eval_pool.py` from repo root and commit the output. |
| annotate.html "File not on GitHub yet" | `pipeline/eval/judgments.json` doesn't exist until first save | Normal — save creates it. |
| "Reset all" in curate.html nuked decisions | `clearAll()` wipes local state; the next save overwrites remote (last-writer-wins) | Restore `pipeline/curation.json` from git history (`git log -- pipeline/curation.json`), commit the restore. |

## Hard rules

- **Never decode GitHub API content with bare `atob()`.** It mojibakes any
  UTF-8 beyond Latin-1; the save path encodes UTF-8, so one round-trip of a
  name like `jalapeño` corrupts the file (AUDIT §4 — found latent, fixed with
  `TextDecoder`).
- **Never record a merge except through `recordMerge` (or a copy with
  identical merge logic).** Bypassing it created 126 chains that silently
  destroyed pairing edges at deploy (AUDIT §§1–2).
- **Never offer deleted or merged-away names as merge candidates** — merging
  into a ghost is how the chains started.
- **Never let a UI edit `badPairs` or drop unknown curation.json fields.**
  They are hand-maintained; the spread-remote-first pattern is what keeps them
  alive.
- **Never write to `pairings.json` from a tool.** curation.json /
  judgments.json are the only files the UIs may touch (DATA.md invariant 4).
- **Never ship a new standalone HTML page without adding it to
  `navigateFallbackDenylist` and `globIgnores`** — the SW will serve the app
  shell in its place.
- **Never add a translation to only one of curate.html's `frDict` /
  `translateFr.ts`** — the copies must stay in sync (CLAUDE.md).
- **Never delete an eval probe/judgment to make `eval.test.ts` happy** — same
  spirit as the "never delete a probe" rule for `db.test.ts`.

## When to STOP and ask the owner (txmnzia, samuelouden@gmail.com)

- Any hand-edit to `pipeline/curation.json` that deletes or rewrites existing
  decisions (as opposed to the UIs appending new ones) — that is a destructive
  data change; confirm before merging.
- Anything that would rename ingredients or change the deployed ingredient
  count — that is `pairings.json` sign-off territory (see the
  edit-pairing-data skill).
- Changing the last-writer-wins sync model or the token storage model — the
  current design is an explicitly accepted trade-off.
