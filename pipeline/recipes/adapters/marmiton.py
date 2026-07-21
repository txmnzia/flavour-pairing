#!/usr/bin/env python3
"""
Marmiton CSV -> normalized JSONL adapter (issue #56).

Consumes the committed Marmiton ingredient table published at
github.com/lvaudor/tuto_texte_Marmiton (data/tib_ingredients.csv): one row per
ingredient line with columns `url, recette, quantites, ingredients` for ~1000
French recipes. Rows are grouped by recipe url; each ingredient line is reduced
to a bare phrase with the French parser, then emitted as the same normalized
JSONL the other adapters produce (mapping to canonical happens downstream in
build_recipes.py).

    # fetch the raw table (kept out of git; see pipeline/corpora/*/raw/):
    curl -sSL -o pipeline/corpora/marmiton/raw/tib_ingredients.csv \\
      https://raw.githubusercontent.com/lvaudor/tuto_texte_Marmiton/master/data/tib_ingredients.csv
    python3 pipeline/recipes/adapters/marmiton.py \\
      pipeline/corpora/marmiton/raw/tib_ingredients.csv > marmiton.jsonl

Only derived fields (title, parsed ingredient phrases, source url) are emitted;
the recipe method text is never touched. The shipped recipes.json links each
entry back to its marmiton.org url.
"""
import csv
import json
import os
import sys
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from adapters.french import parse_fr_line  # noqa: E402

csv.field_size_limit(1 << 24)


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: marmiton.py <tib_ingredients.csv> [> out.jsonl]")

    recipes = OrderedDict()  # url -> {title, lines[]}
    with open(sys.argv[1], encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            url = (row.get("url") or "").strip()
            if not url:
                continue
            rec = recipes.setdefault(url, {"title": (row.get("recette") or "").strip(),
                                           "lines": []})
            rec["lines"].append(row.get("ingredients") or "")

    for i, (url, rec) in enumerate(recipes.items()):
        if not rec["title"]:
            continue
        phrases = [p for p in (parse_fr_line(l) for l in rec["lines"]) if p]
        if not phrases:
            continue
        out = {
            "id": f"marmiton-{i}",
            "title": rec["title"],
            "lang": "fr",
            "ingredients": phrases,
            "url": url if url.startswith("http") else "https://" + url,
            "source": "marmiton",
        }
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
