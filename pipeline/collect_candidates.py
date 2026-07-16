#!/usr/bin/env python3
"""Requests-only variant of rank_images.py for PIL-less environments.

Same job as rank_images.py (issue #48, IMAGE_RANKING_RUNBOOK.md step 1): for
each target ingredient, fetch EVERY image in its Wikipedia article, keep the
free-licensed rasters, download thumbnails, and lay them out for visual ranking.

Differences from rank_images.py:
  * downloads raw thumbnail bytes with `requests` (no Pillow re-encode), and
  * builds each montage with headless Chromium (an HTML grid -> screenshot)
    instead of Pillow — so it runs where pip/PIL are unavailable but Wikimedia
    egress and a Chromium binary exist.

Resumable: an ingredient whose <slug>/candidates.json already exists is skipped
unless --force. Output lives under pipeline/image_candidates/<slug>/ (gitignored).

Usage:
  python3 pipeline/collect_candidates.py                 # scored <3 + missing tiles
  python3 pipeline/collect_candidates.py --only garlic
  python3 pipeline/collect_candidates.py --scores-le 3   # also the 3s
  python3 pipeline/collect_candidates.py --missing-only
"""

import argparse
import csv
import html
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_images as fi  # reuse tested API + filtering helpers

ROOT = Path(__file__).resolve().parent.parent
AUDIT_CSV = ROOT / "pipeline" / "image_audit.csv"
CAND_DIR = ROOT / "pipeline" / "image_candidates"
MIN_WIDTH = 300
MAX_CANDIDATES = 12  # cap for a readable 3-wide montage; heuristic orders best-first
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
COMMONS_MODE = False  # set by --commons: search all of Commons instead of the article
# Homonym noise a bare Commons text-search drags in (bourbon-the-town, black-bean
# aphids, portraits, maps, stamps, disease photos): demote so food images surface.
COMMONS_JUNK = {
    "aphid", "aphids", "aphis", "portrait", "portraits", "map", "town", "city",
    "village", "county", "street", "church", "building", "station", "coat",
    "arms", "flag", "coin", "coins", "stamp", "banknote", "cigarette", "poster",
    "logo", "disease", "rot", "blight", "pest", "larva", "larvae", "moth",
    "beetle", "caterpillar", "fungus", "mould", "mold", "person", "man", "woman",
    "player", "band", "album", "church", "castle", "river", "mountain", "island",
}
DL_SLEEP = 0.4  # politeness delay between image downloads (upload.wikimedia.org 429s otherwise)


def _get_bytes(url: str) -> bytes:
    """GET image bytes, honouring 429 rate limiting with backoff."""
    for attempt in range(5):
        r = fi.session.get(url, timeout=60)
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 0)) or (2 ** attempt)
            time.sleep(min(wait, 30))
            continue
        r.raise_for_status()
        return r.content
    r.raise_for_status()
    return r.content


def target_names(args) -> list[str]:
    live = fi.live_ingredients()
    live_set = set(live)
    if args.names_file:
        names = json.loads(Path(args.names_file).read_text())
        if isinstance(names, dict):  # accept {"targets": [...]}
            names = names.get("targets", [])
        names = [n for n in names if n in live_set]
        return names[: args.limit] if args.limit else names
    if args.only:
        want = set(args.only)
        return [n for n in live if n in want]
    by_slug = {fi.slugify(n): n for n in live}
    tiles = set()
    scored = set()
    if AUDIT_CSV.exists():
        for row in csv.DictReader(AUDIT_CSV.open()):
            tiles.add(row["slug"])
            if int(row["score"]) <= args.scores_le and row["slug"] in by_slug:
                scored.add(by_slug[row["slug"]])
    missing = [n for s, n in by_slug.items() if s not in tiles]
    if args.missing_only:
        names = missing
    elif args.scored_only:
        names = list(scored)
    else:
        names = sorted(set(missing) | scored, key=lambda n: n.lower())
    return names[: args.limit] if args.limit else names


COMMONS_API = "https://commons.wikimedia.org/w/api.php"


def commons_candidates(name: str) -> list[dict]:
    """Search Wikimedia Commons directly (not just the ingredient's article) for
    free-licensed raster photos of the ingredient. This is the coverage lever:
    an article may embed no free image while Commons holds dozens."""
    try:
        r = fi.session.get(COMMONS_API, params={
            "action": "query", "format": "json", "generator": "search",
            "gsrsearch": f"filetype:bitmap {name}", "gsrnamespace": "6",
            "gsrlimit": "40", "prop": "imageinfo",
            "iiprop": "extmetadata|size|url|user", "iiurlwidth": str(fi.THUMB_WIDTH),
        }, timeout=30)
        r.raise_for_status()
        time.sleep(fi.SLEEP)
        pages = (r.json().get("query", {}) or {}).get("pages", {}) or {}
    except (requests.RequestException, ValueError):
        return []
    cands = []
    for p in pages.values():
        f = p.get("title", "").removeprefix("File:")
        ext = f.lower().rsplit(".", 1)[-1] if "." in f else ""
        if ext not in ("jpg", "jpeg", "png", "webp") or fi.SCAN_JUNK_RE.search(f):
            continue
        ii = (p.get("imageinfo") or [{}])[0]
        em = ii.get("extmetadata", {}) or {}
        lic = (em.get("LicenseShortName", {}) or {}).get("value", "")
        w = ii.get("width", 0) or 0
        if not fi.license_ok(lic) or w < MIN_WIDTH or not ii.get("thumburl"):
            continue
        artist = re.sub(r"<[^>]+>", "", (em.get("Artist", {}) or {}).get("value", "")).strip()
        cands.append({
            "file": f, "license": lic, "artist": artist,
            "description_url": ii.get("descriptionurl", ""),
            "width": w, "thumb_url": ii.get("thumburl", ""),
        })
    return cands


def collect(name: str) -> dict:
    ov = (fi.overrides_cache or {}).get(name, {})
    title = ov.get("title", name)
    if COMMONS_MODE:
        cands = _heuristic_order(name, name, commons_candidates(name))[:MAX_CANDIDATES]
        return {"name": name, "title": f"Commons search: {name}", "candidates": cands}
    files = [f for f in fi.article_image_files(title)
             if not fi.SCAN_JUNK_RE.search(f)
             and f.lower().rsplit(".", 1)[-1] in ("jpg", "jpeg", "png", "webp")]
    cands = []
    if files:
        details = fi.fetch_file_details(files)
        for f in files:
            d = details.get(f.replace(" ", "_"))
            if not d or d.get("mediatype") not in ("", "BITMAP", "DRAWING"):
                continue
            if not fi.license_ok(d.get("license", "")) or (d.get("width") or 0) < MIN_WIDTH:
                continue
            cands.append({
                "file": f, "license": d.get("license", ""),
                "artist": d.get("artist", ""), "description_url": d.get("description_url", ""),
                "width": d.get("width", 0), "thumb_url": d.get("thumb_url", ""),
            })
        cands = _heuristic_order(name, title, cands)[:MAX_CANDIDATES]
    return {"name": name, "title": title, "candidates": cands}


def _heuristic_order(name, title, cands):
    want = set(fi._tokens(name)) | set(fi._tokens(title))

    def matches(toks):
        n = 0
        for w in want:
            if len(w) < 3:
                n += w in toks
            elif any(t == w or (len(t) >= 3 and (t.startswith(w) or w.startswith(t))) for t in toks):
                n += 1
        return n

    def score(c):
        tset = set(fi._tokens(c["file"]))
        return (3.0 * matches(tset) + 1.5 * len(fi.SCAN_BONUS & tset)
                - 3.5 * len(fi.SCAN_PENALTY & tset)
                - 4.0 * len(COMMONS_JUNK & tset)  # demote homonym noise from a Commons search
                + min((c.get("width") or 0) / 1500.0, 2.0))

    return sorted(cands, key=score, reverse=True)


def download_thumbs(out_dir: Path, cands: list[dict]) -> list[dict]:
    saved = []
    for i, c in enumerate(cands):
        u = c.get("thumb_url")
        if not u:
            continue
        ext = u.rsplit(".", 1)[-1].split("?")[0].lower()
        if ext not in ("jpg", "jpeg", "png", "webp"):
            ext = "jpg"
        fn = f"{i:02d}.{ext}"
        try:
            (out_dir / fn).write_bytes(_get_bytes(u))
            c["thumb_file"] = fn
            saved.append(c)
            time.sleep(DL_SLEEP)
        except requests.RequestException as e:
            print(f"     skip {c['file']}: {e}")
    return saved


def build_montage(out_dir: Path, meta: dict) -> None:
    cands = meta["candidates"]
    if not cands:
        return
    cells = []
    for i, c in enumerate(cands):
        fn = c.get("thumb_file", "")
        lbl = html.escape(f"{i}. {c['file'][:38]}")
        meta_lbl = html.escape(f"{c['license']} · {c['width']}px")
        img = f'<img src="{html.escape(fn)}">' if fn else '<div class=miss>no thumb</div>'
        cells.append(f'<div class=cell>{img}<div class=lbl>{lbl}</div>'
                     f'<div class=meta>{meta_lbl}</div></div>')
    title = html.escape(f"{meta['name']}  —  article: {meta['title']}  ({len(cands)} candidates)")
    page = (
        "<!doctype html><meta charset=utf8><style>"
        "body{margin:0;background:#222;font-family:sans-serif}"
        "h1{color:#eee;font-size:16px;padding:8px 10px;margin:0}"
        ".grid{display:grid;grid-template-columns:repeat(3,250px);gap:8px;padding:8px}"
        ".cell{width:250px}"
        ".cell img{width:250px;height:250px;object-fit:contain;background:#f5f5f5;display:block}"
        ".miss{width:250px;height:250px;background:#444;color:#999;display:flex;"
        "align-items:center;justify-content:center}"
        ".lbl{color:#fff;font-size:13px;padding:2px 0 0}"
        ".meta{color:#9c9;font-size:12px}"
        "</style>"
        f"<h1>{title}</h1><div class=grid>{''.join(cells)}</div>"
    )
    (out_dir / "montage.html").write_text(page)
    rows = (len(cands) + 2) // 3
    h = 40 + rows * (250 + 40) + 20
    subprocess.run(
        [CHROME, "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
         "--force-device-scale-factor=1", f"--window-size=810,{h}",
         f"--screenshot={out_dir/'montage.png'}", str(out_dir / "montage.html")],
        capture_output=True, timeout=120,
    )


def main() -> int:
    global MAX_CANDIDATES, COMMONS_MODE
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--scores-le", type=int, default=2)
    ap.add_argument("--missing-only", action="store_true")
    ap.add_argument("--scored-only", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true", help="re-collect even if candidates.json exists")
    ap.add_argument("--names-file", help="JSON list (or {'targets':[...]}) of ingredient names to collect")
    ap.add_argument("--max", type=int, default=MAX_CANDIDATES, help="max candidates per article")
    ap.add_argument("--index-file", default="index.json", help="index filename (use distinct names for parallel shards)")
    ap.add_argument("--commons", action="store_true", help="search all of Commons instead of the article's own images")
    args = ap.parse_args()

    MAX_CANDIDATES = args.max
    COMMONS_MODE = args.commons

    fi.overrides_cache = json.loads(fi.OVERRIDES.read_text()) if fi.OVERRIDES.exists() else {}
    names = target_names(args)
    CAND_DIR.mkdir(parents=True, exist_ok=True)
    index_path = CAND_DIR / args.index_file
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    print(f"{len(names)} ingredient(s) to collect")
    for k, name in enumerate(names, 1):
        slug = fi.slugify(name)
        out_dir = CAND_DIR / slug
        if (out_dir / "candidates.json").exists() and not args.force:
            print(f"  [{k}/{len(names)}] {name}: cached, skip")
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            meta = collect(name)
            meta["candidates"] = download_thumbs(out_dir, meta["candidates"])
            (out_dir / "candidates.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
            build_montage(out_dir, meta)
        except Exception as e:  # noqa: BLE001
            print(f"  [{k}/{len(names)}] {name}: ERROR {e}")
            continue
        index[name] = {"slug": slug, "title": meta["title"], "n": len(meta["candidates"])}
        index_path.write_text(json.dumps(index, indent=1, ensure_ascii=False))
        print(f"  [{k}/{len(names)}] {name}: {len(meta['candidates'])} candidates")
    print(f"\nDone. Montages: {CAND_DIR}/<slug>/montage.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
