#!/usr/bin/env python3
"""
RecipeNLG -> normalized JSONL adapter (issue #56).

RecipeNLG (https://recipenlg.cs.put.poznan.pl, ~2.2M English recipes) ships as a
CSV with columns: title, ingredients, directions, link, source, NER. The NER
column is a JSON list of already-extracted ingredient entities -- near-canonical
English, so we use it directly as the ingredient signal and skip line parsing.
We keep only derived fields (title, ingredient entities, source url); the
`directions` text is never emitted (licensing -- see pipeline/DATA.md).

    python3 pipeline/recipes/adapters/recipenlg.py full_dataset.csv > recipenlg.jsonl

The output feeds pipeline/recipes/build_recipes.py unchanged. NOTE: RecipeNLG's
hosts are not reachable from the sandbox's egress policy; run this where the CSV
is available, commit the derived recipes.json, not the raw corpus.
"""
import ast
import csv
import json
import sys

csv.field_size_limit(1 << 24)


def parse_list(cell):
    if not cell:
        return []
    try:
        val = json.loads(cell)
    except (ValueError, TypeError):
        try:
            val = ast.literal_eval(cell)
        except (ValueError, SyntaxError):
            return []
    return [str(x) for x in val] if isinstance(val, list) else []


def normalize_url(link):
    link = (link or "").strip()
    if not link:
        return ""
    return link if link.startswith("http") else "https://" + link


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: recipenlg.py <RecipeNLG csv> [> out.jsonl]")
    with open(sys.argv[1], encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            ner = parse_list(row.get("NER", ""))
            title = (row.get("title") or "").strip()
            if not title or not ner:
                continue
            out = {
                "id": f"recipenlg-{i}",
                "title": title,
                "lang": "en",
                "ingredients": ner,
                "url": normalize_url(row.get("link")),
                "source": "recipenlg",
            }
            sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
