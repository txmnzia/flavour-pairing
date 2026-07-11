#!/usr/bin/env python3
"""Fetch open-licensed ingredient images and process them into uniform tiles.

For every ingredient live in the deployed app (pairings.json minus curation
deletes/merges), this script:

  1. Resolves a Wikipedia article (override -> exact title -> search fallback)
     and takes its lead image (PageImages API).
  2. Checks the file's license via imageinfo/extmetadata and keeps only
     free licenses (CC0 / CC BY / CC BY-SA / public domain / GFDL / ...).
  3. Downloads a thumbnail, removes the background with rembg, trims,
     centers on a transparent square canvas and saves a 256x256 WebP to
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
  , "<ingredient name>": {"skip": true} }

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
SUBJECT_FILL = 0.80  # subject occupies at most this fraction of the tile
THUMB_WIDTH = 512
BATCH = 50
SLEEP = 0.15  # politeness delay between HTTP requests

session = requests.Session()
session.headers["User-Agent"] = UA


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
    """File name (without 'File:') -> {license, artist, description_url}."""
    out: dict[str, dict] = {}
    titles = [f"File:{f}" for f in files]
    for batch in chunked(titles, BATCH):
        data = api_get({
            "action": "query",
            "titles": "|".join(batch),
            "prop": "imageinfo",
            "iiprop": "extmetadata|url",
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
            }
    return out


def process_image(raw: bytes, rembg_session) -> tuple[bytes, float] | None:
    """Background-removed, trimmed, centered TILE_SIZE WebP. Returns (bytes, alpha_coverage)."""
    from PIL import Image
    from rembg import remove

    cut = remove(raw, session=rembg_session)
    im = Image.open(io.BytesIO(cut)).convert("RGBA")
    alpha = im.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        return None
    # Degenerate cutout: subject nearly vanished.
    if (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) < 0.02 * im.width * im.height:
        return None
    im = im.crop(bbox)

    hist = im.getchannel("A").histogram()
    coverage = sum(hist[32:]) / max(1, im.width * im.height)

    side = max(1, int(max(im.size) / SUBJECT_FILL))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
    canvas = canvas.resize((TILE_SIZE, TILE_SIZE), Image.LANCZOS)

    buf = io.BytesIO()
    canvas.save(buf, "WEBP", quality=82, method=6)
    return buf.getvalue(), round(coverage, 3)


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
then cropped and background-removed. Generated {generated} by <code>pipeline/fetch_images.py</code>.</p>
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
    todo: dict[str, str] = {}  # name -> wikipedia title to try
    for name in names:
        ov = overrides.get(name, {})
        if ov.get("skip"):
            report["misses"][name] = "skipped (override)"
            continue
        if not args.force and (OUT_DIR / f"{slugify(name)}.webp").exists():
            continue
        todo[name] = ov.get("title", name)

    print(f"{len(names)} live ingredients, {len(todo)} to fetch")
    if not todo:
        # Still regenerate manifest/attributions from what's on disk.
        finalize(credits, report)
        return 0

    # Pass 1: exact/override titles.
    title_by_name = dict(todo.items())
    resolved = resolve_page_images(sorted(set(title_by_name.values())))

    # Pass 2: search fallback for misses (flagged for review).
    for name, title in title_by_name.items():
        if title in resolved:
            continue
        found = search_title(name)
        if found:
            extra = resolve_page_images([found])
            if found in extra:
                resolved[title] = extra[found]
                report["flags"][name] = f"via search: {found}"
                continue
        report["misses"][name] = "no wikipedia lead image"

    # License metadata for all candidate files.
    files = sorted({r["file"] for r in resolved.values()})
    meta = fetch_file_metadata(files)

    from rembg import new_session
    rembg_session = new_session("u2net")

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
            r = session.get(info["thumb_url"], timeout=60)
            r.raise_for_status()
            time.sleep(SLEEP)
            result = process_image(r.content, rembg_session)
        except Exception as e:  # noqa: BLE001 — record and continue
            report["misses"][name] = f"error: {e}"
            failed += 1
            continue
        if result is None:
            report["misses"][name] = "background removal produced no subject"
            failed += 1
            continue
        data, coverage = result
        (OUT_DIR / f"{slugify(name)}.webp").write_bytes(data)
        credits[name] = {
            "file": info["file"],
            "page_title": info["page_title"],
            "license": m.get("license", ""),
            "artist": m.get("artist", ""),
            "description_url": m.get("description_url", ""),
        }
        if coverage > 0.95:
            report["flags"][name] = (report["flags"].get(name, "") + " full-frame cutout").strip()
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
