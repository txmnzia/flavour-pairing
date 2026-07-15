#!/usr/bin/env python3
"""Fetch EVERY image in an ingredient's Wikipedia article and lay them out for
visual ranking — the collection step of the "rank all, pick the best if > 3"
image-quality pass (issue #48). See pipeline/IMAGE_RANKING_RUNBOOK.md.

Needs network to en.wikipedia.org + upload.wikimedia.org, so it runs in a
session or CI with Wikimedia egress (a plain dev sandbox blocks those hosts —
that is why this is a separate step from the visual ranking Claude does).

For each target ingredient it:
  1. resolves the article: image_overrides.json "title" -> the ingredient name,
  2. lists every File: in that article and drops chrome / maps / diagrams /
     non-raster media,
  3. keeps only free-licensed raster images (width >= MIN_WIDTH),
  4. downloads a THUMB_WIDTH-px thumbnail of each into
     pipeline/image_candidates/<slug>/NN.webp,
  5. writes <slug>/candidates.json (ordered metadata, best-guess first) and
     <slug>/montage.png (a labelled grid for ranking).

It does NOT choose or cut out anything. A human/Claude then ranks each
montage with the 0-5 rubric and records the winner:
  * top score  > 3  ->  {"file": "<winning Commons file>"} in image_overrides.json
  * top score <= 3  ->  {"skip": true}
Running `python3 pipeline/fetch_images.py --force` afterwards downloads the
pinned file and builds the final background-removed tile through the tested
process_image() path.

Usage:
  python3 pipeline/rank_images.py                 # all tiles scored <= 2 in image_audit.csv
  python3 pipeline/rank_images.py --scores-le 3   # also the middling tiles
  python3 pipeline/rank_images.py --only garlic --only "star anise"
  python3 pipeline/rank_images.py --all           # every live ingredient
"""

import argparse
import csv
import io
import json
import sys
from pathlib import Path

import requests

import fetch_images as fi  # reuse the tested API + filtering helpers

ROOT = Path(__file__).resolve().parent.parent
AUDIT_CSV = ROOT / "pipeline" / "image_audit.csv"
CAND_DIR = ROOT / "pipeline" / "image_candidates"
MIN_WIDTH = 300
MAX_CANDIDATES = 30  # cap busy articles; they are ordered best-guess first


def targets(args) -> list[str]:
    """Ingredient names to collect candidates for."""
    live = fi.live_ingredients()
    if args.only:
        return [n for n in live if n in set(args.only)]
    if args.all:
        return live[: args.limit] if args.limit else live
    # default: the audit queue — slugs at or below the score threshold
    by_slug = {fi.slugify(n): n for n in live}
    picked = []
    if AUDIT_CSV.exists():
        for row in csv.DictReader(AUDIT_CSV.open()):
            if int(row["score"]) <= args.scores_le and row["slug"] in by_slug:
                picked.append(by_slug[row["slug"]])
    return picked[: args.limit] if args.limit else picked


def heuristic_order(name: str, title: str, cands: list[dict]) -> list[dict]:
    """Order candidates best-guess-first so the montage's early tiles are the
    likely winners (mirrors fetch_images.resolve_scanned_image scoring)."""
    want = set(fi._tokens(name)) | set(fi._tokens(title))

    def matches(toks: set[str]) -> int:
        n = 0
        for w in want:
            if len(w) < 3:
                n += w in toks
            elif any(t == w or (len(t) >= 3 and (t.startswith(w) or w.startswith(t))) for t in toks):
                n += 1
        return n

    def score(c: dict) -> float:
        tset = set(fi._tokens(c["file"]))
        return (3.0 * matches(tset)
                + 1.5 * len(fi.SCAN_BONUS & tset)
                - 3.5 * len(fi.SCAN_PENALTY & tset)
                + min((c.get("width") or 0) / 1500.0, 2.0))

    return sorted(cands, key=score, reverse=True)


def collect(name: str) -> dict | None:
    ov = (fi.overrides_cache or {}).get(name, {})
    title = ov.get("title", name)
    files = [f for f in fi.article_image_files(title)
             if not fi.SCAN_JUNK_RE.search(f)
             and f.lower().rsplit(".", 1)[-1] in ("jpg", "jpeg", "png", "webp")]
    if not files:
        return {"name": name, "title": title, "candidates": [], "note": "no images in article"}
    details = fi.fetch_file_details(files)
    cands = []
    for f in files:
        d = details.get(f.replace(" ", "_"))
        if not d or d.get("mediatype") not in ("", "BITMAP", "DRAWING"):
            continue
        if not fi.license_ok(d.get("license", "")) or (d.get("width") or 0) < MIN_WIDTH:
            continue
        cands.append({
            "file": f,
            "license": d.get("license", ""),
            "artist": d.get("artist", ""),
            "description_url": d.get("description_url", ""),
            "width": d.get("width", 0),
            "thumb_url": d.get("thumb_url", ""),
        })
    cands = heuristic_order(name, title, cands)[:MAX_CANDIDATES]
    return {"name": name, "title": title, "candidates": cands}


def build_montage(slug: str, meta: dict, out_dir: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont
    import math

    cands = meta["candidates"]
    if not cands:
        return
    tile, pad, label_h, cols = 240, 10, 46, 5
    rows = math.ceil(len(cands) / cols)
    cellw, cellh = tile + pad * 2, tile + pad * 2 + label_h
    canvas = Image.new("RGB", (cols * cellw, rows * cellh), (32, 32, 36))
    draw = ImageDraw.Draw(canvas)
    try:
        big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except Exception:  # noqa: BLE001
        big = small = ImageFont.load_default()
    for i, c in enumerate(cands):
        r, col = divmod(i, cols)
        x0, y0 = col * cellw, r * cellh
        cell = Image.new("RGB", (tile, tile), (245, 245, 245))
        p = out_dir / f"{i:02d}.webp"
        if p.exists():
            try:
                im = Image.open(p).convert("RGB")
                im.thumbnail((tile, tile), Image.LANCZOS)
                cell.paste(im, ((tile - im.width) // 2, (tile - im.height) // 2))
            except Exception:  # noqa: BLE001
                pass
        canvas.paste(cell, (x0 + pad, y0 + pad))
        fn = c["file"][:34] + ("…" if len(c["file"]) > 34 else "")
        draw.text((x0 + pad, y0 + pad + tile + 2), f"{i}. {fn}", fill=(255, 255, 255), font=small)
        draw.text((x0 + pad, y0 + pad + tile + 20), f"{c['license']}  {c['width']}px", fill=(150, 200, 150), font=small)
    canvas.save(out_dir / "montage.png")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", default=[], help="ingredient name(s)")
    ap.add_argument("--all", action="store_true", help="every live ingredient")
    ap.add_argument("--scores-le", type=int, default=2, help="audit-score ceiling for the default queue")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    fi.overrides_cache = json.loads(fi.OVERRIDES.read_text()) if fi.OVERRIDES.exists() else {}
    names = targets(args)
    print(f"{len(names)} ingredient(s) to collect candidates for")
    CAND_DIR.mkdir(parents=True, exist_ok=True)
    index = {}
    for k, name in enumerate(names, 1):
        slug = fi.slugify(name)
        out_dir = CAND_DIR / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            meta = collect(name)
        except Exception as e:  # noqa: BLE001
            print(f"  [{k}/{len(names)}] {name}: ERROR {e}")
            continue
        for i, c in enumerate(meta["candidates"]):
            if not c.get("thumb_url"):
                continue
            try:
                r = fi.session.get(c["thumb_url"], timeout=60)
                r.raise_for_status()
                from PIL import Image
                im = Image.open(io.BytesIO(r.content)).convert("RGB")
                im.thumbnail((fi.THUMB_WIDTH, fi.THUMB_WIDTH), Image.LANCZOS)
                im.save(out_dir / f"{i:02d}.webp", "WEBP", quality=80)
            except (requests.RequestException, OSError) as e:
                print(f"     skip {c['file']}: {e}")
        (out_dir / "candidates.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
        build_montage(slug, meta, out_dir)
        index[name] = {"slug": slug, "title": meta["title"], "n": len(meta["candidates"])}
        print(f"  [{k}/{len(names)}] {name}: {len(meta['candidates'])} candidates")
    (CAND_DIR / "index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False))
    print(f"\nDone. Montages under {CAND_DIR}/<slug>/montage.png — rank them per the runbook.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
