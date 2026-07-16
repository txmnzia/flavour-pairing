#!/usr/bin/env python3
"""Fetch open-licensed ingredient images and process them into uniform tiles.

For every ingredient live in the deployed app (pairings.json minus curation
deletes/merges), this script:

  1. Resolves a Wikipedia article (override -> exact title -> search fallback)
     and takes its lead image (PageImages API).
  2. Checks the file's license via imageinfo/extmetadata and keeps only
     free licenses (CC0 / CC BY / CC BY-SA / public domain / GFDL / ...).
  3. Downloads a thumbnail, centre-crops it to a square (background KEPT —
     no cut-out) and saves a 256x256 WebP to
     web/public/ingredient-images/<slug>.webp.
  4. Writes web/public/ingredient-images/manifest.json (slugs the client
     checks before rendering an <img>), pipeline/image_credits.json
     (attribution source of truth), web/public/attributions.html
     (generated credits page) and pipeline/image_fetch_report.json
     (misses + review flags).

Ingredients without a usable image simply stay on the emoji fallback.

Network: needs en.wikipedia.org + upload.wikimedia.org. Designed to run in
CI (.github/workflows/fetch-images.yml) because dev sandboxes may block
those hosts. Re-runs are incremental: existing .webp files are skipped
unless --force is given.

Manual fixes go in pipeline/image_overrides.json:
  { "<ingredient name>": {"title": "Wikipedia article title"}
  , "<ingredient name>": {"file": "Exact Commons file name.jpg"}
  , "<ingredient name>": {"skip": true} }

Tile criteria (issue #48 feedback): subject centered and filling the frame,
ideally a single specimen, no humans in frame (enforced via face detection
when OpenCV is installed), and the food form rather than the live animal
(enforced via overrides, e.g. chicken -> "Chicken as food").

Usage:
  python3 pipeline/fetch_images.py [--limit N] [--only NAME] [--force]
"""

import argparse
import io
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from html import escape
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
PAIRINGS = ROOT / "web" / "public" / "pairings.json"
CURATION = ROOT / "pipeline" / "curation.json"
OVERRIDES = ROOT / "pipeline" / "image_overrides.json"
OUT_DIR = ROOT / "web" / "public" / "ingredient-images"
CREDITS = ROOT / "pipeline" / "image_credits.json"
REPORT = ROOT / "pipeline" / "image_fetch_report.json"
ATTRIBUTIONS_HTML = ROOT / "web" / "public" / "attributions.html"

API = "https://en.wikipedia.org/w/api.php"
UA = "FlavourPairingImageBot/1.0 (https://github.com/txmnzia/flavour-pairing)"
TILE_SIZE = 256
THUMB_WIDTH = 512
BATCH = 50
SLEEP = 0.25  # politeness delay between HTTP requests

session = requests.Session()
session.headers["User-Agent"] = UA


def download_bytes(url: str) -> bytes:
    """GET image bytes, honouring 429 rate limiting with backoff.

    upload.wikimedia.org throttles bulk fetches (a --force rebuild of ~800
    tiles hammered it into 429s), so retry on 429 respecting Retry-After.
    """
    for attempt in range(6):
        r = session.get(url, timeout=60)
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 0)) or 2 ** attempt
            time.sleep(min(wait, 30))
            continue
        r.raise_for_status()
        time.sleep(SLEEP)
        return r.content
    r.raise_for_status()
    return r.content


def slugify(name: str) -> str:
    """Must stay identical to ingredientSlug() in web/src/utils/ingredientImage.ts."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower())
    return s.strip("-")


def live_ingredients() -> list[str]:
    """Deployed ingredient list: pairings.json names minus curation deletes/merge sources."""
    names = json.loads(PAIRINGS.read_text())["i"]
    cur = json.loads(CURATION.read_text())
    deleted = set(cur.get("deleted", []))
    merged = set(cur.get("merged", {}))
    return [n for n in names if n not in deleted and n not in merged]


def api_get(params: dict) -> dict:
    params = {"format": "json", "formatversion": "2", **params}
    for attempt in range(4):
        try:
            r = session.get(API, params=params, timeout=30)
            r.raise_for_status()
            time.sleep(SLEEP)
            return r.json()
        except (requests.RequestException, ValueError):
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def resolve_page_images(titles: list[str]) -> dict[str, dict]:
    """title -> {file, thumb_url} for pages that have a lead image."""
    out: dict[str, dict] = {}
    for batch in chunked(titles, BATCH):
        data = api_get({
            "action": "query",
            "titles": "|".join(batch),
            "prop": "pageimages",
            "piprop": "thumbnail|name",
            "pithumbsize": str(THUMB_WIDTH),
            "redirects": "1",
        })
        query = data.get("query", {})
        # Map normalisation/redirect chains back to the requested title.
        back: dict[str, str] = {}
        for m in query.get("normalized", []) + query.get("redirects", []):
            back[m["to"]] = m["from"]

        def original(title: str) -> str:
            seen = set()
            while title in back and title not in seen:
                seen.add(title)
                title = back[title]
            return title

        for page in query.get("pages", []):
            req = original(page.get("title", ""))
            if page.get("pageimage") and page.get("thumbnail", {}).get("source"):
                out[req] = {
                    "file": page["pageimage"],
                    "thumb_url": page["thumbnail"]["source"],
                    "page_title": page["title"],
                }
    return out


def search_title(name: str) -> str | None:
    data = api_get({
        "action": "query",
        "list": "search",
        "srsearch": name,
        "srlimit": "1",
        "srnamespace": "0",
    })
    hits = data.get("query", {}).get("search", [])
    return hits[0]["title"] if hits else None


FREE_LICENSE_RE = re.compile(
    r"(cc0|public domain|pd-|^pd$|no restrictions|cc[- ]by(?!.*(nc|nd))|gfdl|attribution|copyrighted free use|mit|apache)",
    re.IGNORECASE,
)


def license_ok(short_name: str) -> bool:
    if not short_name:
        return False
    if re.search(r"nc|nd|fair use|non-free", short_name, re.IGNORECASE):
        return False
    return bool(FREE_LICENSE_RE.search(short_name))


def strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html or "").strip()


def fetch_file_metadata(files: list[str]) -> dict[str, dict]:
    """File name (without 'File:') -> {license, artist, description_url, thumb_url}."""
    out: dict[str, dict] = {}
    titles = [f"File:{f}" for f in files]
    for batch in chunked(titles, BATCH):
        data = api_get({
            "action": "query",
            "titles": "|".join(batch),
            "prop": "imageinfo",
            "iiprop": "extmetadata|url",
            "iiurlwidth": str(THUMB_WIDTH),
        })
        for page in data.get("query", {}).get("pages", []):
            infos = page.get("imageinfo") or []
            if not infos:
                continue
            meta = infos[0].get("extmetadata", {})
            # PageImages returns file names with underscores; imageinfo page
            # titles use spaces. Key on the underscore form so lookups match.
            out[page["title"].removeprefix("File:").replace(" ", "_")] = {
                "license": meta.get("LicenseShortName", {}).get("value", ""),
                "artist": strip_tags(meta.get("Artist", {}).get("value", "")),
                "description_url": infos[0].get("descriptionurl", ""),
                "thumb_url": infos[0].get("thumburl", ""),
            }
    return out


# Filenames that are never the ingredient photo: chrome, icons, maps, diagrams,
# non-raster media. Used by scan mode to skip an article's non-content images.
SCAN_JUNK_RE = re.compile(
    r"(commons-logo|wiki|\bicon\b|\.svg$|\.ogg$|\.oga$|\.ogv$|\.webm$|\.mid$|\.pdf$|\.tif$|\.tiff$|"
    r"\bmap\b|distribution|range|locator|\bflag\b|coat[_ ]of[_ ]arms|\bseal\b|"
    r"ambox|question[_ ]book|edit-|padlock|symbol|barnstar|nuvola|crystal[_ ]clear|"
    r"diagram|chart|graph|\bplate\b|illustration|drawing|engraving|botanical|herbarium)",
    re.IGNORECASE,
)
# Tokens that mark the wrong subject (the living plant/animal, not the food form)
# or a poor tile; penalised so a scan prefers the culinary specimen.
SCAN_PENALTY = {"plant", "plants", "tree", "trees", "flower", "flowers", "flowering",
                "leaf", "leaves", "foliage", "seedling", "sapling", "field", "garden",
                "orchard", "wild", "growing", "bush", "shrub", "vine", "blossom",
                "live", "alive", "animal", "bird", "whole", "farm", "crop", "harvest"}
# Tokens that mark the desired culinary/prepared form; rewarded.
SCAN_BONUS = {"dried", "seed", "seeds", "powder", "ground", "roasted", "peeled",
              "sliced", "cut", "bowl", "pile", "heap", "closeup", "close-up", "macro",
              "food", "cooked", "raw", "fresh", "ripe", "pod", "pods", "kernel",
              "kernels", "grain", "grains", "root", "roots", "bulb", "bulbs", "clove",
              "cloves", "fruit", "fruits", "berry", "berries", "nut", "nuts", "paste",
              "jar", "bottle", "isolated", "white"}


def article_image_files(title: str) -> list[str]:
    """All File: names embedded in an article, in article order."""
    data = api_get({
        "action": "query",
        "titles": title,
        "prop": "images",
        "imlimit": "max",
        "redirects": "1",
    })
    out: list[str] = []
    for page in data.get("query", {}).get("pages", []):
        for im in page.get("images", []) or []:
            out.append(im["title"].removeprefix("File:"))
    return out


def fetch_file_details(files: list[str]) -> dict[str, dict]:
    """Like fetch_file_metadata but also returns width + mediatype for ranking."""
    out: dict[str, dict] = {}
    titles = [f"File:{f}" for f in files]
    for batch in chunked(titles, BATCH):
        data = api_get({
            "action": "query",
            "titles": "|".join(batch),
            "prop": "imageinfo",
            "iiprop": "extmetadata|url|size|mediatype",
            "iiurlwidth": str(THUMB_WIDTH),
        })
        for page in data.get("query", {}).get("pages", []):
            infos = page.get("imageinfo") or []
            if not infos:
                continue
            info = infos[0]
            meta = info.get("extmetadata", {})
            out[page["title"].removeprefix("File:").replace(" ", "_")] = {
                "license": meta.get("LicenseShortName", {}).get("value", ""),
                "artist": strip_tags(meta.get("Artist", {}).get("value", "")),
                "description_url": info.get("descriptionurl", ""),
                "thumb_url": info.get("thumburl", ""),
                "width": info.get("width", 0),
                "mediatype": (info.get("mediatype") or "").upper(),
            }
    return out


def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t]


def resolve_scanned_image(name: str, title: str) -> dict | None:
    """Pick the most relevant free-licensed photo among *all* images in an article.

    Answers "does the article have a better image than its lead?" — the lead
    (PageImages) is often the living plant while the culinary form (seeds, root,
    bulb, dried pods) sits further down. Opt in with
    {"title": "X", "scan": true} in image_overrides.json.
    """
    files = [f for f in article_image_files(title)
             if not SCAN_JUNK_RE.search(f)
             and f.lower().rsplit(".", 1)[-1] in ("jpg", "jpeg", "png", "webp")]
    if not files:
        return None
    details = fetch_file_details(files)
    want = set(_tokens(name)) | set(_tokens(title))

    def name_matches(toks: set[str]) -> int:
        """Count want-tokens present in the filename, stem-aware so that e.g.
        'pepper' matches 'peppercorns' and 'root' matches 'roots'."""
        n = 0
        for w in want:
            if len(w) < 3:
                n += w in toks
            elif any(t == w or (len(t) >= 3 and (t.startswith(w) or w.startswith(t))) for t in toks):
                n += 1
        return n

    best = None
    best_score = -1e9
    for order, f in enumerate(files):
        d = details.get(f.replace(" ", "_"))
        if not d or d.get("mediatype") not in ("", "BITMAP", "DRAWING"):
            continue
        if not license_ok(d.get("license", "")) or (d.get("width") or 0) < 200:
            continue
        tset = set(_tokens(f))
        score = 3.0 * name_matches(tset)                     # matches the ingredient
        score += 1.5 * len(SCAN_BONUS & tset)                # culinary-form words
        score -= 3.5 * len(SCAN_PENALTY & tset)              # plant/animal/whole-specimen words
        score += min((d.get("width") or 0) / 1500.0, 2.0)    # prefer larger sources
        score -= 0.15 * order                                # mild lead-first tiebreak
        if score > best_score:
            best_score, best = score, (f, d)
    if best is None:
        return None
    f, d = best
    return {"file": f, "thumb_url": d.get("thumb_url", ""), "page_title": title}


_face_cascades = None
_face_check_broken = False


def contains_human(raw: bytes) -> bool | None:
    """Face detection on the source photo. None = check unavailable (skipped).

    Never raises: a broken OpenCV install (e.g. OpenCV 5 removed
    CascadeClassifier) must degrade to "check skipped", not fail the fetch.
    Requires opencv-python-headless 4.x (pinned in the workflow).
    """
    global _face_cascades, _face_check_broken
    if _face_check_broken:
        return None
    try:
        import cv2
        import numpy as np

        if _face_cascades is None:
            _face_cascades = [
                cv2.CascadeClassifier(cv2.data.haarcascades + name)
                for name in ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml")
            ]
        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return None
        h, w = img.shape[:2]
        if max(h, w) > 800:
            s = 800 / max(h, w)
            img = cv2.resize(img, (int(w * s), int(h * s)))
        gray = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
        for cascade in _face_cascades:
            # minNeighbors high to keep false positives rare on food textures
            if len(cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(40, 40))):
                return True
        return False
    except Exception as e:  # noqa: BLE001
        _face_check_broken = True
        print(f"WARNING: face detection unavailable ({e}) — human check skipped")
        return None


def process_image(raw: bytes, rembg_session=None) -> tuple[bytes, float] | None:
    """Square, centre-cropped photo TILE_SIZE WebP — the background is KEPT.

    Background removal (rembg) was dropped: cut-outs of low-contrast or
    full-frame subjects (seeds, grains, powders, herbs) looked poor and often
    failed the ghost-cutout gate. A plain square crop of the source photo is
    more reliable and more attractive. `rembg_session` is accepted but unused.
    Returns (bytes, 1.0); None only if the image can't be decoded.
    """
    from PIL import Image, ImageOps

    try:
        im = Image.open(io.BytesIO(raw))
        im = ImageOps.exif_transpose(im).convert("RGB")
    except Exception:  # noqa: BLE001 — unreadable/corrupt image
        return None
    w, h = im.size
    side = min(w, h)
    if side < 1:
        return None
    left, top = (w - side) // 2, (h - side) // 2
    im = im.crop((left, top, left + side, top + side)).resize(
        (TILE_SIZE, TILE_SIZE), Image.LANCZOS)

    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=82, method=6)
    return buf.getvalue(), 1.0


def build_attributions_html(credits: dict) -> str:
    rows = []
    for name in sorted(credits):
        c = credits[name]
        artist = escape(c.get("artist") or "unknown author")
        lic = escape(c.get("license") or "")
        url = escape(c.get("description_url") or c.get("page_url") or "#")
        rows.append(
            f'<li><strong>{escape(name)}</strong> — <a href="{url}" rel="noreferrer">'
            f"{escape(c.get('file', 'source'))}</a> by {artist} ({lic})</li>"
        )
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Image credits — Flavour Pairing</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #1a1a2e; color: #eee; max-width: 720px; margin: 0 auto; padding: 2rem 1rem; }}
  a {{ color: #9ab; }}
  h1 {{ font-size: 1.3rem; }}
  li {{ margin-bottom: .4rem; font-size: .85rem; }}
</style>
</head>
<body>
<h1>Image credits</h1>
<p>Ingredient images are sourced from Wikipedia / Wikimedia Commons under free licenses,
then cropped to a square tile. Generated {generated} by <code>pipeline/fetch_images.py</code>.</p>
<ul>
{chr(10).join(rows)}
</ul>
<p><a href="./">← Back to the app</a></p>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0, help="process at most N ingredients (0 = all)")
    ap.add_argument("--only", action="append", default=[], help="process only these ingredient names")
    ap.add_argument("--force", action="store_true", help="re-fetch even if the .webp already exists")
    args = ap.parse_args()

    overrides = json.loads(OVERRIDES.read_text()) if OVERRIDES.exists() else {}
    credits = json.loads(CREDITS.read_text()) if CREDITS.exists() else {}

    names = live_ingredients()
    if args.only:
        names = [n for n in names if n in set(args.only)]
    if args.limit:
        names = names[: args.limit]

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    report = {"generated": datetime.now(timezone.utc).isoformat(), "misses": {}, "flags": {}}

    by_slug: dict[str, list[str]] = {}
    for n in names:
        by_slug.setdefault(slugify(n), []).append(n)
    collisions = {s: ns for s, ns in by_slug.items() if len(ns) > 1}
    if collisions:
        report["flags"]["_slug_collisions"] = collisions

    file_by_name: dict[str, str] = {}  # direct Commons-file overrides
    scan_by_name: dict[str, str] = {}  # name -> article to scan for its best image
    todo: dict[str, str] = {}  # name -> wikipedia title to try
    for name in names:
        ov = overrides.get(name, {})
        if ov.get("skip"):
            report["misses"][name] = "skipped (override)"
            continue
        if not args.force and (OUT_DIR / f"{slugify(name)}.webp").exists():
            continue
        if ov.get("file"):
            file_by_name[name] = ov["file"].removeprefix("File:").replace(" ", "_")
        elif ov.get("scan"):
            scan_by_name[name] = ov.get("title", name)
        else:
            todo[name] = ov.get("title", name)

    print(f"{len(names)} live ingredients, "
          f"{len(todo) + len(file_by_name) + len(scan_by_name)} to fetch")
    if not todo and not file_by_name and not scan_by_name:
        # Still regenerate manifest/attributions from what's on disk.
        finalize(credits, report)
        return 0

    # Pass 1: exact/override titles.
    title_by_name = dict(todo.items())
    resolved = resolve_page_images(sorted(set(title_by_name.values())))

    # Pass 2: search fallback for misses (flagged for review). Names with an
    # explicit override never fall back — a generic search would resurrect
    # exactly the image the override was written to avoid.
    for name, title in title_by_name.items():
        if title in resolved:
            continue
        if name in overrides:
            report["misses"][name] = f"override title not found: {title}"
            continue
        found = search_title(name)
        if found:
            extra = resolve_page_images([found])
            if found in extra:
                resolved[title] = extra[found]
                report["flags"][name] = f"via search: {found}"
                continue
        report["misses"][name] = "no wikipedia lead image"

    # Scan overrides: pick the most relevant image among all of an article's
    # images, not just its (often wrong) lead. Never fall back to search — the
    # scan was requested precisely to look inside a known article.
    for name, title in scan_by_name.items():
        try:
            picked = resolve_scanned_image(name, title)
        except Exception as e:  # noqa: BLE001 — record and continue
            report["misses"][name] = f"scan error: {e}"
            continue
        if picked is None:
            report["misses"][name] = f"scan: no suitable image in {title}"
            continue
        key = f"__scan__{name}"
        title_by_name[name] = key
        resolved[key] = picked
        report["flags"][name] = (report["flags"].get(name, "") + f" scanned: {picked['file']}").strip()

    # Direct Commons-file overrides become synthetic resolutions; the thumb
    # URL comes from imageinfo below.
    for name, f in file_by_name.items():
        title_by_name[name] = f"__file__{name}"
        resolved[f"__file__{name}"] = {"file": f, "thumb_url": "", "page_title": f"File:{f}"}

    # License metadata for all candidate files.
    files = sorted({r["file"] for r in resolved.values()})
    meta = fetch_file_metadata(files)

    for name, f in file_by_name.items():
        m = meta.get(f.replace(" ", "_"), {})
        if m.get("thumb_url"):
            resolved[f"__file__{name}"]["thumb_url"] = m["thumb_url"]
        else:
            report["misses"][name] = "override file not found on Commons"
            del resolved[f"__file__{name}"]

    ok = failed = 0
    for name, title in sorted(title_by_name.items()):
        info = resolved.get(title)
        if info is None:
            continue
        m = meta.get(info["file"].replace(" ", "_"), {})
        if not license_ok(m.get("license", "")):
            report["misses"][name] = f"license not free: {m.get('license') or 'unknown'}"
            continue
        try:
            content = download_bytes(info["thumb_url"])
            # Haar cascades false-positive heavily on food textures (a 2026-07
            # run flagged 171/800 tiles including plain couscous), so a face
            # hit only flags the tile for manual review in images.html —
            # it never blocks the fetch.
            if contains_human(content):
                report["flags"][name] = (report["flags"].get(name, "") + " possible human — review").strip()
            result = process_image(content)
        except Exception as e:  # noqa: BLE001 — record and continue
            report["misses"][name] = f"error: {e}"
            failed += 1
            continue
        if result is None:
            report["misses"][name] = "could not decode image"
            failed += 1
            continue
        data, _ = result
        (OUT_DIR / f"{slugify(name)}.webp").write_bytes(data)
        credits[name] = {
            "file": info["file"],
            "page_title": info["page_title"],
            "license": m.get("license", ""),
            "artist": m.get("artist", ""),
            "description_url": m.get("description_url", ""),
        }
        ok += 1
        if ok % 25 == 0:
            print(f"  {ok} images done…")

    print(f"fetched {ok}, failed {failed}, misses {len(report['misses'])}")
    finalize(credits, report)
    return 0


def finalize(credits: dict, report: dict) -> None:
    """Write manifest (from files actually on disk), credits, report, attributions page."""
    slugs = sorted(p.stem for p in OUT_DIR.glob("*.webp"))
    live_slugs = {slugify(n) for n in live_ingredients()}
    stale = [s for s in slugs if s not in live_slugs]
    if stale:
        report["flags"]["_stale_files"] = stale  # curation drift; harmless, listed for cleanup

    manifest = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "count": len(slugs),
        "slugs": slugs,
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1))
    CREDITS.write_text(json.dumps(credits, indent=1, ensure_ascii=False, sort_keys=True))
    REPORT.write_text(json.dumps(report, indent=1, ensure_ascii=False, sort_keys=True))
    if credits:
        ATTRIBUTIONS_HTML.write_text(build_attributions_html(credits))
    coverage = len(slugs) / max(1, len(live_slugs))
    print(f"manifest: {len(slugs)} images, coverage {coverage:.0%} of live ingredients")


if __name__ == "__main__":
    sys.exit(main())
