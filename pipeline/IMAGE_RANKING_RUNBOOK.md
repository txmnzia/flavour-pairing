# Ingredient image ranking runbook (issue #48)

**Goal (what to build in the networked session):** for each ingredient, fetch
**every** image in its Wikipedia article, **rank** them by the quality rubric
below, take the **highest-ranked** one, and use it **only if its score is above
3** (i.e. a 4 or 5). If nothing in the article clears the bar, **fall back to
the emoji tile**. This replaces "take the article's lead image", which is what
produced the current low-quality tiles.

This runbook is a cold-start handoff: it carries all the context, the rubric,
the tooling, and the exact steps. You do not need the prior conversation.

---

## Why this is a separate session

Direct Wikipedia access is blocked by this environment's **egress policy** — the
proxy returns `403 CONNECT` for `en.wikipedia.org`, `commons.wikimedia.org` and
`upload.wikimedia.org`. WebSearch works (different path) but cannot download
images. So the collection + fetch steps must run in a session (or the
`fetch-images.yml` GitHub workflow) that has **Wikimedia egress**. First thing
to do: confirm access.

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  "https://en.wikipedia.org/w/api.php?action=query&format=json&titles=Garlic&prop=pageimages"
# 200 = good. 403/000 = still blocked; you cannot run the fetch here.
pip install requests pillow "rembg[cpu]"   # deps for fetch_images.py
```

Work on the existing branch `claude/ingredient-image-audit-s0vg32` (or branch
from it). Images are assets — they never affect pairing data and need no data
sign-off. Never work directly on `main`; the fetch results are reviewed on the
`ingredient-images-assets` branch before merge.

---

## The ranking rubric (0–5) — calibrated with the owner

Score each **candidate image** on how well it would represent the ingredient as
a recommendation-card tile. Accuracy dominates: a beautiful photo of the wrong
thing is useless.

| Score | Meaning |
|------:|---------|
| **5** | Correct canonical form, clean/isolable subject, well framed, appealing. |
| **4** | Correct & clean, minor nit (framing/appeal). |
| **3** | Recognizable but a real flaw — mediocre/busy source, or a slightly-off form. |
| **2** | Poor — wrong *form* of the right thing, or a source that will cut out badly. |
| **1** | Wrong subject entirely (the living plant/animal, a diagram, logo, map). |

Calibration decisions to honour:
- **A prepared dish is acceptable if it clearly reads as the ingredient** — do
  not penalize "it's a dish, not the raw item" on its own; judge clarity/appeal.
- Prefer the **culinary form people expect**: the seed/root/bulb/nut/dried pod,
  not the flowering plant; the meat, not the live animal; the product, not a
  brand logo or a store shelf.
- Favour a **single, centered specimen on a plain background** — it makes a
  clean background-removed tile. A busy scene or a tiny subject scores lower
  even if technically correct.

**The gate:** accept the top-ranked candidate only if its score is **> 3**
(4 or 5). Otherwise set the ingredient to `skip` (emoji fallback). This is
deliberately strict — better an emoji than a mediocre photo.

---

## Procedure

### 1. Collect candidates (needs network)

`pipeline/rank_images.py` fetches every image in each target article, drops
chrome/maps/diagrams/non-raster, keeps only free-licensed rasters (≥300 px),
downloads a thumbnail of each, and writes a labelled montage + metadata.

```bash
python3 pipeline/rank_images.py                 # default: the 157 tiles scored <=2
python3 pipeline/rank_images.py --scores-le 3   # also the 188 middling tiles
python3 pipeline/rank_images.py --only garlic --only "star anise"
python3 pipeline/rank_images.py --all           # every live ingredient (~950)
```

Output per ingredient: `pipeline/image_candidates/<slug>/`
- `montage.png` — a grid of every candidate, index-labelled with license + size,
  ordered best-guess-first.
- `candidates.json` — ordered metadata: `file`, `license`, `artist`,
  `description_url`, `width`, `thumb_url`.
- `NN.webp` — the downloaded thumbnails (indices match the montage).
- `pipeline/image_candidates/index.json` — the run manifest.

### 2. Rank each montage (visual — this is the actual "ranking")

Open each `montage.png` and score its candidates with the rubric. Record, per
ingredient, the **index + filename of the highest-scoring candidate and its
score**. The heuristic already ordered them, but trust your eyes over the order.

### 3. Apply the gate → write overrides

Edit `pipeline/image_overrides.json` (keyed by **ingredient name**, not slug):

- Top score **> 3** → pin that exact Commons file:
  ```json
  "garlic": { "file": "Garlic bulbs and cloves.jpg" }
  ```
- Top score **≤ 3** (nothing good enough) → emoji fallback:
  ```json
  "adobo sauce": { "skip": true }
  ```

Credits (artist/license/URL) are captured automatically by `fetch_images.py`
from the file's imageinfo — you do not hand-write them. A `{"file": …}` pin with
a non-free or missing license is rejected at fetch time (→ emoji), so a wrong
license just fails safe.

> The current `image_overrides.json` already holds an **interim** automated
> pass: 4 pinned files, 113 `{"title":…, "scan":true}` entries, 54 `skip`.
> `scan` is a *heuristic* auto-pick (filename-based, no visual gate) built for
> when this session had no network — see "scan mode" below. The ranking pass
> **supersedes** those: replace each `scan`/`skip` entry with a vetted
> `{"file":…}` or a confirmed `{"skip":true}` as you rank. Anything you don't
> get to keeps working via `scan`.

### 4. Build the tiles (needs network)

```bash
# only the ones you changed:
python3 pipeline/fetch_images.py --force --only garlic --only "adobo sauce"
# or the whole queue at once:
python3 pipeline/fetch_images.py --force
```

`fetch_images.py` downloads each pinned/scanned/name-resolved source, removes
the background (rembg u2net), trims, centers on a 256×256 transparent canvas,
runs the QC gate (rejects ghost cutouts), and writes
`web/public/ingredient-images/<slug>.webp` plus the regenerated `manifest.json`,
`image_credits.json`, `attributions.html`, and `image_fetch_report.json`.

### 5. Review, validate, ship

```bash
# spot-check new tiles visually (open them, or build a montage like the audit did)
python3 -c "import json,pathlib; d=pathlib.Path('web/public/ingredient-images'); \
m=json.loads((d/'manifest.json').read_text()); disk=sorted(p.stem for p in d.glob('*.webp')); \
assert m['slugs']==disk and m['count']==len(disk); print('manifest OK', len(disk))"
python3 pipeline/validate_pairings.py     # images don't touch data, sanity only
cd web && npm test && npm run build && cd ..
```

Review the changed tiles on the `ingredient-images-assets` branch (the workflow
pushes there; force-push each run). When they look right, merge to `main` — a
normal merge, no data sign-off. The deploy workflow ships them. Note the SW
caches tiles CacheFirst for 90 days, so a changed tile may look stale to
returning users until the cache expires.

---

## Scope

The `image_audit.csv` scores every one of the 806 tiles that existed at audit
time. Suggested order:

1. **The replacement queue** — 157 live tiles scored ≤ 2 (`rank_images.py`
   default). Highest value.
2. **The middling tiles** — the 3s (`--scores-le 3`, ~345 total). Optional
   upgrade pass; the gate means many will land on emoji, which is fine.
3. **Everything** (`--all`) — only if you want to re-pick better images for the
   current 4s/5s too. Large; not required.

Two **high-priority commons** in the queue: `garlic` (article lead is the whole
plant, not bulbs) and `star anise` (lead is leaves, not the star pods).

---

## File inventory

| Path | What it is |
|------|-----------|
| `pipeline/image_audit.csv` | Every tile scored 1–5 with category + reason (audit source of truth). |
| `pipeline/image_audit_worklist.md` | Human-readable per-ingredient resolution (file / scan / skip). |
| `pipeline/rank_images.py` | **Collect** step — fetch all article images → montage + candidates.json. |
| `pipeline/image_candidates/<slug>/` | Generated candidates + montage for ranking (safe to delete/regenerate). |
| `pipeline/fetch_images.py` | **Build** step — pin/scan/name → background-removed tile + manifest + credits. |
| `pipeline/image_overrides.json` | The one hand-edited input: `{name: {file|title+scan|skip}}`. |
| `web/public/ingredient-images/*.webp` + `manifest.json` | The tiles + the list the client renders. Commit together. |
| `pipeline/image_credits.json` → `web/public/attributions.html` | Attribution (free licenses legally require it) — generated, never hand-edit. |

Guardrails (from the `ingredient-images` skill — read it too):
- **Never weaken the license gate** (`license_ok` rejects `nc|nd|fair use|non-free`).
- **Never lower the QC gate** (<4% solid alpha → reject; it exists because rembg
  produced invisible "ghost" tiles).
- **`slugify()` here must stay byte-identical to `ingredientSlug()`** in
  `web/src/utils/ingredientImage.ts` — the slug is the name↔file join key.
- Do **not** commit `web/public/pairings.db` (build artifact) or `web/dist/`.
- Images never affect scoring; no `pairings.json` sign-off applies.

---

## Appendix — `scan` mode (the interim automation)

`fetch_images.py` gained an opt-in `scan` mode: `{"title":"X","scan":true}`
makes the fetcher enumerate **all** images in article X, drop junk, keep
free-licensed rasters, and score them (stem-aware name match + culinary-form
bonus + plant/animal penalty + size) to auto-pick one — the programmatic cousin
of this runbook's visual ranking. It has no quality gate and cannot judge
appeal, so it is a fallback, not the destination. The point of the networked
ranking pass is to replace those auto-picks with **eyes-on**, gated choices.
`resolve_scanned_image()` in `fetch_images.py` is the reference scorer if you
want to tune the heuristic ordering used by `rank_images.py`.
