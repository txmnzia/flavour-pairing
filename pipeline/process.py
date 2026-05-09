#!/usr/bin/env python3
"""
Pipeline: recipes → pairings.json (+ optional SQLite)

Sources
-------
  --source huggingface   Download RecipeNLG via HuggingFace datasets (default)
  --source csv           Use a local RecipeNLG CSV (--input path required)

Usage
-----
  # Recommended: stream from HuggingFace, process up to 500k recipes
  python process.py --limit 500000 --json-output ../web/public/pairings.json

  # Use a local CSV downloaded from https://recipenlg.cs.put.poznan.pl/
  python process.py --source csv --input data/full_dataset.csv \\
                    --json-output ../web/public/pairings.json

The JSON output is what the web app loads at runtime.
"""

import argparse
import ast
import json
import math
import sqlite3
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from tqdm import tqdm

# ---------------------------------------------------------------------------
# Cuisine detection
# ---------------------------------------------------------------------------

CUISINE_KEYWORDS: dict[str, list[str]] = {
    "French": [
        "french", "dijon", "gratin", "ratatouille", "cassoulet", "bouillabaisse",
        "quiche", "soufflé", "souffle", "beurre", "crème", "creme", "croissant",
        "baguette", "coq au vin", "vichyssoise", "lyonnaise", "provençal",
        "provencal", "nicoise", "béarnaise", "hollandaise", "velouté", "bisque",
        "dauphinois", "bourguignon", "blanquette", "tarragon", "herbes de provence",
    ],
    "Italian": [
        "italian", "pasta", "risotto", "pizza", "parmigiana", "carbonara",
        "pesto", "bruschetta", "focaccia", "gnocchi", "lasagna", "lasagne",
        "osso buco", "tiramisu", "cannoli", "parmesan", "mozzarella",
        "prosciutto", "pancetta", "pecorino", "arancini", "polenta",
        "bolognese", "amatriciana", "arrabiata",
    ],
    "Mexican": [
        "mexican", "taco", "enchilada", "burrito", "salsa", "guacamole",
        "quesadilla", "tortilla", "tamale", "mole", "pozole",
        "jalapeño", "jalapeno", "chipotle", "cilantro",
    ],
    "Asian": [
        "chinese", "japanese", "korean", "thai", "vietnamese", "asian",
        "stir fry", "stir-fry", "fried rice", "ramen", "pho",
        "dim sum", "sushi", "teriyaki", "tempura", "miso", "pad thai",
        "green curry", "red curry", "tom yum", "banh mi", "bibimbap",
        "kimchi", "dumplings", "wonton",
    ],
    "Indian": [
        "indian", "curry", "masala", "tikka", "dal", "dhal", "biryani",
        "naan", "chapati", "samosa", "korma", "vindaloo", "saag",
        "paneer", "chana", "tandoori", "garam masala",
    ],
    "Mediterranean": [
        "mediterranean", "greek", "hummus", "falafel", "tzatziki",
        "spanakopita", "moussaka", "shawarma", "kebab", "tabbouleh",
        "fattoush", "baba ganoush", "pita", "halloumi",
    ],
    "American": [
        "bbq", "barbecue", "mac and cheese", "fried chicken",
        "cornbread", "clam chowder", "buffalo", "american", "southern",
        "cajun", "creole",
    ],
    "British": [
        "british", "english", "scottish", "shepherd's pie",
        "cottage pie", "fish and chips", "yorkshire", "scone", "pasty",
    ],
}

MIN_INGREDIENT_FREQ = 50
MIN_COOCCURRENCE   = 20
TOP_N_PER_PAIR     = 50


def detect_cuisine(title: str, ingredients: list[str]) -> str:
    text = (title + " " + " ".join(ingredients)).lower()
    for cuisine, keywords in CUISINE_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return cuisine
    return "Other"


def parse_ner(raw) -> list[str]:
    """Accept either a Python list or a JSON/repr string."""
    if isinstance(raw, list):
        return [i.strip().lower() for i in raw if i.strip()]
    try:
        items = ast.literal_eval(str(raw))
        return [i.strip().lower() for i in items if i.strip()]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_from_huggingface(limit: int | None) -> list[tuple[list[str], str]]:
    from datasets import load_dataset  # imported here to keep startup fast

    print("Streaming RecipeNLG from HuggingFace (this may take a few minutes)…")
    ds = load_dataset("recipe_nlg", split="train", streaming=True, trust_remote_code=True)

    records = []
    for i, item in enumerate(tqdm(ds, total=limit or 2_231_142, unit="recipes")):
        if limit and i >= limit:
            break
        ingredients = parse_ner(item.get("ner") or item.get("ingredients", []))
        if len(ingredients) < 2:
            continue
        cuisine = detect_cuisine(str(item.get("title", "")), ingredients)
        records.append((ingredients, cuisine))

    print(f"  {len(records):,} valid recipes loaded")
    return records


def load_from_csv(path: str, limit: int | None) -> list[tuple[list[str], str]]:
    import pandas as pd

    print(f"Loading {path}…")
    df = pd.read_csv(path, usecols=["title", "NER"], nrows=limit)
    df = df.dropna(subset=["NER"])
    print(f"  {len(df):,} rows read")

    records = []
    for _, row in tqdm(df.iterrows(), total=len(df), unit="recipes"):
        ingredients = parse_ner(row["NER"])
        if len(ingredients) < 2:
            continue
        cuisine = detect_cuisine(str(row.get("title", "")), ingredients)
        records.append((ingredients, cuisine))

    print(f"  {len(records):,} valid recipes")
    return records


# ---------------------------------------------------------------------------
# Co-occurrence & NPMI
# ---------------------------------------------------------------------------

def build_counts(records: list[tuple[list[str], str]]) -> tuple[Counter, Counter]:
    single: Counter = Counter()
    pairs:  Counter = Counter()
    for ingredients, _ in records:
        unique = list(set(ingredients))
        for ing in unique:
            single[ing] += 1
        for a, b in combinations(sorted(unique), 2):
            pairs[(a, b)] += 1
    return single, pairs


def npmi(count_ab: int, count_a: int, count_b: int, n: int) -> float:
    if count_ab == 0:
        return -1.0
    p_ab = count_ab / n
    p_a  = count_a  / n
    p_b  = count_b  / n
    pmi  = math.log(p_ab / (p_a * p_b))
    return round(pmi / -math.log(p_ab), 4)


# ---------------------------------------------------------------------------
# SQLite builder
# ---------------------------------------------------------------------------

def build_sqlite(
    records: list[tuple[list[str], str]],
    valid_ingredients: set[str],
    db_path: Path,
) -> sqlite3.Connection:
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE ingredients (
            id   INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            freq INTEGER NOT NULL
        );
        CREATE TABLE cuisines (
            id           INTEGER PRIMARY KEY,
            name         TEXT UNIQUE NOT NULL,
            recipe_count INTEGER NOT NULL
        );
        CREATE TABLE pairings (
            ingredient_a INTEGER NOT NULL,
            ingredient_b INTEGER NOT NULL,
            cuisine_id   INTEGER NOT NULL,
            npmi         REAL NOT NULL,
            cooccurrence INTEGER NOT NULL,
            PRIMARY KEY (ingredient_a, ingredient_b, cuisine_id)
        );
        CREATE INDEX idx_pair_lookup ON pairings (ingredient_a, cuisine_id, npmi DESC);
    """)
    return con


def insert_pairings(cur, single, pairs, valid_ingredients, ing_id, cuisine_id_val, n, min_cooc):
    from itertools import groupby as _groupby
    rows = []
    for (a, b), cnt in pairs.items():
        if a not in valid_ingredients or b not in valid_ingredients:
            continue
        if cnt < min_cooc:
            continue
        score = npmi(cnt, single[a], single[b], n)
        if score <= 0:
            continue
        rows.append((ing_id[a], ing_id[b], cuisine_id_val, score, cnt))
        rows.append((ing_id[b], ing_id[a], cuisine_id_val, score, cnt))

    rows.sort(key=lambda r: (r[0], -r[3]))
    kept = []
    for _, group in _groupby(rows, key=lambda r: r[0]):
        kept.extend(list(group)[:TOP_N_PER_PAIR])

    cur.executemany("INSERT OR IGNORE INTO pairings VALUES (?, ?, ?, ?, ?)", kept)


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------

def export_json(con: sqlite3.Connection, json_path: str) -> None:
    ing_rows = con.execute("SELECT id, name FROM ingredients ORDER BY id").fetchall()
    ingredients = [name for _, name in ing_rows]
    sql_ing_to_idx = {sql_id: idx for idx, (sql_id, _) in enumerate(ing_rows)}

    cuis_rows = con.execute("SELECT id, name FROM cuisines ORDER BY id").fetchall()
    cuis_rows.sort(key=lambda r: (r[1] != "all", r[1]))
    cuisines = [name for _, name in cuis_rows]
    sql_cuis_to_idx = {sql_id: idx for idx, (sql_id, _) in enumerate(cuis_rows)}

    pairings: dict[str, list] = {}
    for a_id, b_id, c_id, score in con.execute(
        "SELECT ingredient_a, ingredient_b, cuisine_id, npmi FROM pairings"
        " ORDER BY cuisine_id, ingredient_a, npmi DESC"
    ).fetchall():
        key = f"{sql_cuis_to_idx[c_id]},{sql_ing_to_idx[a_id]}"
        pairings.setdefault(key, []).append([sql_ing_to_idx[b_id], round(score * 100)])

    data = {"v": 1, "i": ingredients, "c": cuisines, "p": pairings}

    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(data, f, separators=(",", ":"))

    size_mb = out.stat().st_size / 1_048_576
    print(f"\nJSON → {json_path}  ({size_mb:.1f} MB, {len(pairings):,} pairing groups)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process(
    source: str,
    csv_input: str | None,
    limit: int | None,
    db_output: str,
    json_output: str | None,
) -> None:
    # Load records
    if source == "huggingface":
        records = load_from_huggingface(limit)
    else:
        if not csv_input:
            raise ValueError("--input is required when --source csv")
        records = load_from_csv(csv_input, limit)

    n_recipes = len(records)

    # Global counts
    print("\nComputing global co-occurrence counts…")
    global_single, global_pairs = build_counts(records)

    valid_ingredients = {i for i, c in global_single.items() if c >= MIN_INGREDIENT_FREQ}
    print(f"  {len(valid_ingredients):,} ingredients meet frequency threshold (≥{MIN_INGREDIENT_FREQ} recipes)")

    # Group by cuisine
    cuisine_records: dict[str, list] = defaultdict(list)
    for rec in records:
        cuisine_records[rec[1]].append(rec)

    # Build SQLite
    db_path = Path(db_output)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = build_sqlite(records, valid_ingredients, db_path)
    cur = con.cursor()

    # Ingredients
    sorted_ings = sorted(valid_ingredients)
    cur.executemany(
        "INSERT INTO ingredients (name, freq) VALUES (?, ?)",
        [(i, global_single[i]) for i in sorted_ings],
    )
    ing_id = {
        name: row[0]
        for name, row in zip(
            sorted_ings,
            cur.execute("SELECT id FROM ingredients ORDER BY id").fetchall(),
        )
    }

    # Cuisines
    cuisine_names = ["all"] + sorted(cuisine_records.keys())
    cur.executemany(
        "INSERT INTO cuisines (name, recipe_count) VALUES (?, ?)",
        [("all", n_recipes)] + [(c, len(cuisine_records[c])) for c in cuisine_names[1:]],
    )
    cuisine_id = {
        name: row[0]
        for name, row in zip(
            cuisine_names,
            cur.execute("SELECT id FROM cuisines ORDER BY id").fetchall(),
        )
    }

    # Global pairings
    print("Computing global pairings…")
    insert_pairings(cur, global_single, global_pairs, valid_ingredients,
                    ing_id, cuisine_id["all"], n_recipes, MIN_COOCCURRENCE)
    con.commit()

    # Per-cuisine pairings
    print("Computing per-cuisine pairings…")
    for cuisine, recs in tqdm(cuisine_records.items(), unit="cuisine"):
        if len(recs) < 500:
            continue
        s, p = build_counts(recs)
        insert_pairings(cur, s, p, valid_ingredients, ing_id,
                        cuisine_id[cuisine], len(recs), MIN_COOCCURRENCE)
    con.commit()

    row_count = con.execute("SELECT COUNT(*) FROM pairings").fetchone()[0]
    size_mb = db_path.stat().st_size / 1_048_576
    print(f"\nSQLite → {db_output}  ({size_mb:.1f} MB, {row_count:,} pairing rows)")

    # JSON export
    if json_output:
        export_json(con, json_output)

    con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["huggingface", "csv"], default="huggingface")
    parser.add_argument("--input", help="Path to RecipeNLG CSV (required for --source csv)")
    parser.add_argument("--limit", type=int, default=None, help="Max recipes to process")
    parser.add_argument("--output", default="/tmp/pairings.db", help="SQLite output path")
    parser.add_argument("--json-output", default=None, help="JSON output path for web app")
    args = parser.parse_args()

    process(
        source=args.source,
        csv_input=args.input,
        limit=args.limit,
        db_output=args.output,
        json_output=args.json_output,
    )
