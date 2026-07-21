#!/usr/bin/env python3
"""
French recipe dump -> normalized JSONL adapter (issue #56).

French corpora (e.g. a Marmiton/CuisineAZ dump) list ingredients as free-text
lines like "250 g de crème fraîche épaisse". This adapter turns each line into a
bare ingredient phrase ("crème fraîche") following ENRICHMENT.md §2, then emits
the same normalized JSONL the English adapter does. The mapping cascade
(pipeline/recipes/mapping.py) resolves the French phrases to canonical names via
the inverted FR dictionary + aliases.

Input is flexible because dumps vary -- JSONL or CSV, ingredients as a JSON list
or a delimited string:

    python3 pipeline/recipes/adapters/french.py dump.jsonl \
        --title-key nom --ingredients-key ingredients --url-key url > french.jsonl

Only derived fields are emitted (title, parsed ingredient phrases, url). Raw
corpora stay gitignored (pipeline/corpora/<corpus>/raw/); commit the derived
recipes.json. French dataset hosts may be blocked by the sandbox egress policy;
run this where the dump is available.
"""
import argparse
import csv
import json
import re
import sys

csv.field_size_limit(1 << 24)

UNITS = (
    "g", "kg", "mg", "l", "cl", "ml", "dl",
    "c", "cs", "cc", "cuillère", "cuillères", "cuiller", "cuillere", "cuilleres",
    "sachet", "sachets", "pincée", "pincées", "gousse", "gousses",
    "tranche", "tranches", "feuille", "feuilles", "brin", "brins",
    "branche", "branches", "botte", "bottes", "boîte", "boîtes",
    "pot", "pots", "verre", "verres", "tasse", "tasses", "pièce", "pièces",
    "filet", "filets", "zeste", "zestes", "noix", "morceau", "morceaux",
    "rondelle", "rondelles", "poignée", "poignées", "kg", "cà",
)
PARTITIVES = ("de la ", "de l'", "d'", "du ", "des ", "de ", "la ", "le ", "les ", "l'", "au ", "à ")
# Preparation clauses cut from the tail. Deliberately excludes freshness words
# (frais/fraîche/sec) which are part of compound names like "crème fraîche" --
# the mapping stage folds those; over-cutting a name is worse than keeping it.
PREP = (
    "haché", "hachée", "hachés", "hachées", "émincé", "émincée", "émincés",
    "râpé", "râpée", "râpés", "coupé", "coupée", "coupés", "coupées",
    "fondu", "fondue", "battu", "battue", "tamisé", "écrasé", "écrasée",
    "ciselé", "ciselée", "épluché", "épluchée", "dénoyauté", "surgelé",
    "surgelée", "en dés", "en tranches", "en morceaux", "en rondelles",
    "facultatif", "facultative", "selon goût",
)

QTY = re.compile(r"^\s*[\d.,/½¼¾⅓⅔\s-]+")
# Multiword measures ("cuillère(s) à soupe/café", "c. à s.") stripped up front:
# drop everything through the "à soupe/café" (or abbreviated "à s./c.") measure,
# regardless of how the spoon word is spelled/accented.
UNIT_PHRASE = re.compile(
    r"^.*?\b(?:à|a)\s*(?:soupe|caf[eé]|s\.|c\.)\.?\s*(?:de\s+|d')?",
    re.IGNORECASE,
)


def parse_fr_line(line):
    s = line.strip().lower()
    if not s:
        return ""
    # 1. strip leading quantity
    s = QTY.sub("", s).strip()
    # 1b. strip a multiword measure ("cuillères à soupe") if present
    s = UNIT_PHRASE.sub("", s).strip()
    # 2. strip a leading unit token, then the partitive that follows
    parts = s.split(" ", 1)
    if parts and parts[0].rstrip(".") in UNITS and len(parts) > 1:
        s = parts[1]
    for part in PARTITIVES:
        if s.startswith(part):
            s = s[len(part):]
            break
    # 3. cut trailing preparation clauses
    s = s.split(",", 1)[0]
    for prep in PREP:
        s = re.sub(r"\b" + re.escape(prep) + r"\b.*$", "", s)
    # 4. tidy
    return re.sub(r"\s+", " ", s).strip(" .-")


def read_records(path, title_key, ing_key, url_key):
    if path.endswith(".jsonl"):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)
    elif path.endswith(".json"):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        yield from (data if isinstance(data, list) else data.get("recipes", []))
    else:  # csv
        with open(path, encoding="utf-8", newline="") as f:
            yield from csv.DictReader(f)


def to_lines(raw):
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        try:
            val = json.loads(raw)
            if isinstance(val, list):
                return [str(x) for x in val]
        except (ValueError, TypeError):
            pass
        return re.split(r"[\n;|]+", raw)
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--title-key", default="title")
    ap.add_argument("--ingredients-key", default="ingredients")
    ap.add_argument("--url-key", default="url")
    args = ap.parse_args()

    for i, rec in enumerate(read_records(args.path, args.title_key,
                                         args.ingredients_key, args.url_key)):
        title = str(rec.get(args.title_key, "")).strip()
        if not title:
            continue
        phrases = [p for p in (parse_fr_line(l)
                               for l in to_lines(rec.get(args.ingredients_key)))
                   if p]
        if not phrases:
            continue
        out = {
            "id": f"french-{i}",
            "title": title,
            "lang": "fr",
            "ingredients": phrases,
            "url": str(rec.get(args.url_key, "")).strip(),
            "source": "french",
        }
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
