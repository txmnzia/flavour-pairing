#!/usr/bin/env python3
"""
Pipeline: RecipeNLG CSV → pairings.db (SQLite)

Usage:
    python process.py --input data/full_dataset.csv --output ../web/public/pairings.db

Download RecipeNLG from: https://recipenlg.cs.put.poznan.pl/
The CSV has columns: title, ingredients, directions, link, source, NER
The NER column contains a JSON list of normalized ingredient names.
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
import pandas as pd

# --- Cuisine detection via title/ingredient keywords ---

CUISINE_KEYWORDS = {
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
        "quesadilla", "tortilla", "tamale", "mole", "pozole", "chile",
        "jalapeño", "jalapeno", "chipotle", "cilantro", "cotija",
    ],
    "Asian": [
        "chinese", "japanese", "korean", "thai", "vietnamese", "asian",
        "stir fry", "stir-fry", "fried rice", "noodle", "ramen", "pho",
        "dim sum", "sushi", "teriyaki", "tempura", "miso", "pad thai",
        "green curry", "red curry", "tom yum", "banh mi", "bibimbap",
        "kimchi", "dumplings", "wonton", "lo mein",
    ],
    "Indian": [
        "indian", "curry", "masala", "tikka", "dal", "dhal", "biryani",
        "naan", "chapati", "samosa", "korma", "vindaloo", "saag",
        "paneer", "chana", "tandoori", "garam masala", "turmeric",
    ],
    "Mediterranean": [
        "mediterranean", "greek", "hummus", "falafel", "tzatziki",
        "spanakopita", "moussaka", "shawarma", "kebab", "tabouleh",
        "tabbouleh", "fattoush", "baba ganoush", "pita", "halloumi",
    ],
    "American": [
        "bbq", "barbecue", "burger", "mac and cheese", "fried chicken",
        "biscuit", "cornbread", "chili", "clam chowder", "buffalo",
        "american", "southern", "cajun", "creole",
    ],
    "British": [
        "british", "english", "scottish", "welsh", "shepherd's pie",
        "cottage pie", "fish and chips", "bangers", "yorkshire", "scone",
        "crumpet", "pasty", "cornish",
    ],
}

MIN_INGREDIENT_FREQ = 50   # must appear in at least N recipes
MIN_COOCCURRENCE = 20      # pair must co-occur in at least N recipes
TOP_N_PER_INGREDIENT = 50  # store top N pairings per (ingredient, cuisine)


def detect_cuisine(title: str, ingredients: list[str]) -> str:
    text = (title + " " + " ".join(ingredients)).lower()
    for cuisine, keywords in CUISINE_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return cuisine
    return "Other"


def parse_ner(raw: str) -> list[str]:
    try:
        items = ast.literal_eval(raw)
        return [i.strip().lower() for i in items if i.strip()]
    except Exception:
        return []


def compute_npmi(count_ab: int, count_a: int, count_b: int, n_recipes: int) -> float:
    if count_ab == 0 or count_a == 0 or count_b == 0:
        return -1.0
    p_ab = count_ab / n_recipes
    p_a = count_a / n_recipes
    p_b = count_b / n_recipes
    pmi = math.log(p_ab / (p_a * p_b))
    npmi = pmi / -math.log(p_ab)
    return round(float(npmi), 4)


def export_recipes_json(
    json_path: str,
    recipe_samples: list[tuple[str, list[str]]],
    valid_ingredients: set[str],
) -> None:
    """Write a standalone recipes.json with titles + filtered ingredient names."""
    recipe_data = []
    for title, ing_names in recipe_samples:
        valid = [n for n in ing_names if n in valid_ingredients]
        if len(valid) >= 2:
            recipe_data.append([title, valid])

    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump({"v": 1, "r": recipe_data}, f, separators=(",", ":"))

    size_kb = out.stat().st_size / 1024
    print(f"  Recipes JSON → {json_path} ({len(recipe_data)} recipes, {size_kb:.0f} KB)")


MAX_RECIPE_SAMPLE = 10_000  # cap stored recipes to keep recipes.json manageable


def process(input_path: str, output_path: str, recipes_output: str | None = None) -> None:
    print(f"Loading {input_path}...")
    df = pd.read_csv(input_path, usecols=["title", "NER"])
    df = df.dropna(subset=["NER"])
    print(f"  {len(df):,} recipes loaded")

    # Parse ingredients and detect cuisine
    print("Parsing ingredients and detecting cuisines...")
    records = []
    raw_recipes: list[tuple[str, list[str]]] = []  # (title, ingredient_names)
    for _, row in tqdm(df.iterrows(), total=len(df)):
        ingredients = parse_ner(row["NER"])
        if len(ingredients) < 2:
            continue
        cuisine = detect_cuisine(str(row.get("title", "")), ingredients)
        records.append((ingredients, cuisine))
        raw_recipes.append((str(row.get("title", "")).strip(), ingredients))

    n_recipes = len(records)
    print(f"  {n_recipes:,} valid recipes")

    # Count single and pair occurrences per cuisine + global
    def build_counts(recs):
        single = Counter()
        pairs = Counter()
        for ingredients, _ in recs:
            unique = list(set(ingredients))
            for ing in unique:
                single[ing] += 1
            for a, b in combinations(sorted(unique), 2):
                pairs[(a, b)] += 1
        return single, pairs

    print("Computing global counts...")
    global_single, global_pairs = build_counts(records)

    # Filter to common ingredients
    valid_ingredients = {i for i, c in global_single.items() if c >= MIN_INGREDIENT_FREQ}
    print(f"  {len(valid_ingredients):,} ingredients meet frequency threshold")

    # Sample recipes for recipes.json: prefer those with most valid ingredients
    if recipes_output:
        scored = [
            (title, ings, sum(1 for i in ings if i in valid_ingredients))
            for title, ings in raw_recipes
            if title
        ]
        scored.sort(key=lambda x: -x[2])
        recipe_samples = [(t, i) for t, i, _ in scored[:MAX_RECIPE_SAMPLE]]

    # Group by cuisine
    cuisine_records: dict[str, list] = defaultdict(list)
    for rec in records:
        cuisine_records[rec[1]].append(rec)

    # --- Build SQLite ---
    db_path = Path(output_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
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
            id   INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
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

    # Insert ingredients
    sorted_ingredients = sorted(valid_ingredients)
    cur.executemany(
        "INSERT INTO ingredients (name, freq) VALUES (?, ?)",
        [(i, global_single[i]) for i in sorted_ingredients],
    )
    ing_id: dict[str, int] = {
        name: row[0]
        for name, row in zip(
            sorted_ingredients,
            cur.execute("SELECT id FROM ingredients ORDER BY id").fetchall(),
        )
    }

    # Insert cuisines (index 0 = "all")
    cuisine_names = ["all"] + sorted(cuisine_records.keys())
    cur.executemany(
        "INSERT INTO cuisines (name, recipe_count) VALUES (?, ?)",
        [("all", n_recipes)]
        + [(c, len(cuisine_records[c])) for c in cuisine_names[1:]],
    )
    cuisine_id: dict[str, int] = {
        name: row[0]
        for name, row in zip(
            cuisine_names,
            cur.execute("SELECT id FROM cuisines ORDER BY id").fetchall(),
        )
    }

    def insert_pairings(single, pairs, cid, n):
        rows = []
        for (a, b), cnt in pairs.items():
            if a not in valid_ingredients or b not in valid_ingredients:
                continue
            if cnt < MIN_COOCCURRENCE:
                continue
            npmi = compute_npmi(cnt, single[a], single[b], n)
            if npmi <= 0:
                continue
            rows.append((ing_id[a], ing_id[b], cid, npmi, cnt))
            rows.append((ing_id[b], ing_id[a], cid, npmi, cnt))  # symmetric

        # Keep only top N per ingredient
        from itertools import groupby
        rows.sort(key=lambda r: (r[0], -r[3]))
        kept = []
        for ing_a, group in groupby(rows, key=lambda r: r[0]):
            kept.extend(list(group)[:TOP_N_PER_INGREDIENT])

        cur.executemany(
            "INSERT OR IGNORE INTO pairings VALUES (?, ?, ?, ?, ?)", kept
        )

    # Global pairings
    print("Computing global pairings...")
    insert_pairings(global_single, global_pairs, cuisine_id["all"], n_recipes)

    # Per-cuisine pairings
    for cuisine, recs in tqdm(cuisine_records.items(), desc="Cuisine pairings"):
        if len(recs) < 200:
            continue
        s, p = build_counts(recs)
        insert_pairings(s, p, cuisine_id[cuisine], len(recs))

    con.commit()
    con.close()

    size_mb = db_path.stat().st_size / 1_048_576
    print(f"\nDone → {output_path} ({size_mb:.1f} MB)")

    if recipes_output:
        export_recipes_json(recipes_output, recipe_samples, valid_ingredients)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/full_dataset.csv")
    parser.add_argument("--output", default="../web/public/pairings.db")
    parser.add_argument("--recipes-output", default=None)
    args = parser.parse_args()
    process(args.input, args.output, recipes_output=args.recipes_output)
