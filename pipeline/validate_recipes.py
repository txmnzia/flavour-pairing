#!/usr/bin/env python3
"""
Structural validation for web/public/recipes.json (issue #56).

Recipe matching joins on canonical ingredient NAMES resolved against the
DEPLOYED pairings.json, so the invariants that matter are: the corpus vocabulary
is a subset of the deployed ingredient set, every local index is in range, and
every recipe is usable (>=1 ingredient, a link, a known language). Run before
merging any change to recipes.json or the recipe pipeline.

    python3 pipeline/validate_recipes.py

Exits non-zero on the first structural failure. A missing recipes.json is not an
error (the feature is optional and degrades gracefully).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
RECIPES = os.path.join(ROOT, "web", "public", "recipes.json")

sys.path.insert(0, os.path.join(HERE, "recipes"))
from mapping import deployed_names  # noqa: E402


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def main():
    if not os.path.exists(RECIPES):
        print("No recipes.json — skipping (feature is optional).")
        return

    with open(RECIPES, encoding="utf-8") as f:
        doc = json.load(f)

    if doc.get("v") != 2:
        fail(f"expected v==2, got {doc.get('v')}")
    vocab = doc.get("ing")
    rows = doc.get("r")
    if not isinstance(vocab, list) or not isinstance(rows, list):
        fail("missing 'ing' vocabulary or 'r' rows")

    deployed = set(deployed_names())
    missing = [n for n in vocab if n not in deployed]
    if missing:
        fail(f"{len(missing)} vocabulary names not in the deployed ingredient set, "
             f"e.g. {missing[:5]}")

    seen = set()
    for i, row in enumerate(rows):
        if not (isinstance(row, list) and len(row) == 4):
            fail(f"recipe {i}: expected [title, [idx], url, lang], got {row!r:.80}")
        title, idxs, url, lang = row
        if not (isinstance(title, str) and title.strip()):
            fail(f"recipe {i}: empty title")
        if lang not in ("en", "fr"):
            fail(f"recipe {i} ({title!r}): lang must be en/fr, got {lang!r}")
        if not (isinstance(url, str) and url.strip()):
            fail(f"recipe {i} ({title!r}): empty url")
        if not (isinstance(idxs, list) and idxs):
            fail(f"recipe {i} ({title!r}): no ingredients")
        for li in idxs:
            if not (isinstance(li, int) and 0 <= li < len(vocab)):
                fail(f"recipe {i} ({title!r}): local index {li} out of range")
        if len(set(idxs)) != len(idxs):
            fail(f"recipe {i} ({title!r}): duplicate ingredient indices")
        key = (lang, title.strip().lower(), frozenset(idxs))
        if key in seen:
            fail(f"recipe {i} ({title!r}): duplicate recipe")
        seen.add(key)

    n_en = sum(1 for r in rows if r[3] == "en")
    n_fr = sum(1 for r in rows if r[3] == "fr")
    print(f"recipes.json OK: {len(rows)} recipes (en {n_en}, fr {n_fr}), "
          f"{len(vocab)} vocabulary names, all in deployed set.")


if __name__ == "__main__":
    main()
