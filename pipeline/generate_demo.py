#!/usr/bin/env python3
"""
Generate a demo pairings.db without requiring RecipeNLG.

Encodes culinary knowledge as ingredient affinities per cuisine,
then derives NPMI-like scores from those affinities.

Usage:
    python generate_demo.py --output ../web/public/pairings.db
"""

import argparse
import math
import random
import sqlite3
from itertools import combinations
from pathlib import Path

random.seed(42)

# ---------------------------------------------------------------------------
# Ingredient list
# ---------------------------------------------------------------------------

INGREDIENTS = [
    # Aromatics
    "garlic", "onion", "shallot", "leek", "scallion", "chive",
    # Fresh herbs
    "parsley", "thyme", "rosemary", "basil", "oregano", "tarragon",
    "sage", "dill", "mint", "cilantro", "chervil", "bay leaf",
    # Spices
    "black pepper", "cumin", "coriander", "paprika", "turmeric",
    "ginger", "cinnamon", "nutmeg", "cayenne", "saffron", "cardamom",
    "fennel seeds", "star anise", "cloves",
    # Proteins
    "chicken", "beef", "pork", "lamb", "salmon", "tuna", "shrimp",
    "cod", "duck", "eggs", "tofu",
    # Cured/processed meats
    "bacon", "pancetta", "prosciutto", "chorizo", "anchovies",
    # Vegetables
    "tomato", "carrot", "potato", "zucchini", "eggplant", "spinach",
    "mushroom", "bell pepper", "broccoli", "cauliflower", "celery",
    "fennel", "artichoke", "asparagus", "peas", "corn", "leek",
    "cabbage", "kale", "cucumber", "avocado",
    # Dairy
    "butter", "cream", "milk", "parmesan", "gruyere", "mozzarella",
    "feta", "goat cheese", "cheddar", "ricotta",
    # Fats & oils
    "olive oil", "sesame oil", "coconut oil", "vegetable oil",
    # Acids
    "lemon", "lime", "orange", "white wine vinegar", "balsamic vinegar",
    "apple cider vinegar",
    # Wines & alcohol
    "white wine", "red wine", "beer",
    # Sauces & condiments
    "soy sauce", "fish sauce", "tomato paste", "dijon mustard",
    "worcestershire sauce", "hot sauce",
    # Pantry
    "flour", "sugar", "honey", "breadcrumbs", "capers", "olives",
    # Nuts & seeds
    "pine nuts", "almonds", "walnuts", "sesame seeds",
    # Carbs
    "pasta", "rice", "bread",
    # Legumes
    "lentils", "chickpeas", "black beans",
    # Stock
    "chicken stock", "beef stock", "vegetable stock",
]

# Deduplicate (leek appears twice above)
INGREDIENTS = list(dict.fromkeys(INGREDIENTS))

# ---------------------------------------------------------------------------
# Cuisine affinities: ingredient → affinity score [0, 1]
# ---------------------------------------------------------------------------

CUISINE_AFFINITIES: dict[str, dict[str, float]] = {
    "French": {
        "butter": 1.0, "cream": 0.9, "shallot": 0.9, "thyme": 0.85,
        "tarragon": 0.95, "white wine": 0.85, "gruyere": 0.85,
        "parsley": 0.75, "mushroom": 0.75, "duck": 0.85,
        "dijon mustard": 0.9, "chervil": 0.95, "bay leaf": 0.8,
        "garlic": 0.65, "onion": 0.75, "carrot": 0.75, "celery": 0.7,
        "black pepper": 0.65, "potato": 0.6, "leek": 0.8,
        "red wine": 0.75, "lemon": 0.55, "flour": 0.65, "eggs": 0.65,
        "chicken": 0.7, "pork": 0.65, "beef": 0.7, "lamb": 0.6,
        "chicken stock": 0.75, "beef stock": 0.7, "pancetta": 0.65,
        "saffron": 0.55, "nutmeg": 0.6, "sage": 0.5,
        "fennel": 0.55, "asparagus": 0.6, "salmon": 0.55,
    },
    "Italian": {
        "olive oil": 1.0, "garlic": 0.95, "basil": 0.95, "parmesan": 0.95,
        "tomato": 0.9, "mozzarella": 0.85, "oregano": 0.85, "pasta": 0.95,
        "prosciutto": 0.85, "pine nuts": 0.8, "onion": 0.75,
        "lemon": 0.65, "rosemary": 0.75, "white wine": 0.75,
        "spinach": 0.65, "anchovies": 0.75, "capers": 0.75,
        "black pepper": 0.65, "fennel": 0.65, "eggplant": 0.7,
        "zucchini": 0.65, "artichoke": 0.65, "bread": 0.55,
        "balsamic vinegar": 0.7, "pancetta": 0.8, "chicken": 0.65,
        "ricotta": 0.75, "sage": 0.7, "butter": 0.6,
        "vegetable stock": 0.6, "chicken stock": 0.6,
        "olives": 0.7, "shallot": 0.5, "thyme": 0.55,
    },
    "Mexican": {
        "cumin": 0.95, "cilantro": 0.95, "lime": 0.95, "cayenne": 0.8,
        "tomato": 0.85, "garlic": 0.8, "onion": 0.8, "chorizo": 0.85,
        "corn": 0.85, "black beans": 0.8, "paprika": 0.7,
        "bell pepper": 0.7, "avocado": 0.8, "chicken": 0.7,
        "beef": 0.7, "pork": 0.65, "coriander": 0.85,
        "oregano": 0.6, "hot sauce": 0.7, "cheddar": 0.6,
        "lemon": 0.4, "olive oil": 0.5, "vegetable oil": 0.6,
    },
    "Asian": {
        "soy sauce": 1.0, "ginger": 0.95, "sesame oil": 0.95,
        "scallion": 0.85, "garlic": 0.85, "rice": 0.85,
        "fish sauce": 0.8, "lime": 0.75, "sesame seeds": 0.8,
        "shrimp": 0.75, "chicken": 0.7, "beef": 0.65, "tofu": 0.75,
        "mushroom": 0.7, "cabbage": 0.65, "kale": 0.5,
        "cilantro": 0.7, "chive": 0.65, "mint": 0.6,
        "coconut oil": 0.55, "sugar": 0.55, "tuna": 0.6,
        "eggs": 0.55, "vegetable stock": 0.55,
    },
    "Indian": {
        "turmeric": 1.0, "cumin": 0.95, "coriander": 0.95,
        "ginger": 0.9, "garlic": 0.85, "onion": 0.85,
        "tomato": 0.75, "cream": 0.65, "chickpeas": 0.85,
        "lentils": 0.85, "cayenne": 0.8, "cinnamon": 0.75,
        "cardamom": 0.8, "fennel seeds": 0.7, "star anise": 0.65,
        "cloves": 0.7, "chicken": 0.75, "lamb": 0.75,
        "coconut oil": 0.6, "mint": 0.65, "saffron": 0.65,
        "paprika": 0.65, "nutmeg": 0.55, "butter": 0.55,
        "vegetable oil": 0.65, "vegetable stock": 0.55,
    },
    "Mediterranean": {
        "olive oil": 1.0, "garlic": 0.9, "lemon": 0.9,
        "tomato": 0.85, "oregano": 0.85, "feta": 0.85,
        "thyme": 0.75, "rosemary": 0.75, "parsley": 0.75,
        "eggplant": 0.75, "zucchini": 0.7, "chickpeas": 0.75,
        "lamb": 0.75, "salmon": 0.65, "shrimp": 0.65,
        "pine nuts": 0.7, "almonds": 0.65, "mint": 0.65,
        "artichoke": 0.65, "fennel": 0.65, "capers": 0.65,
        "white wine": 0.6, "honey": 0.55, "cucumber": 0.6,
        "olives": 0.8, "anchovies": 0.6, "black pepper": 0.6,
    },
    "American": {
        "cheddar": 0.9, "bacon": 0.9, "butter": 0.8,
        "garlic": 0.7, "onion": 0.75, "black pepper": 0.7,
        "paprika": 0.65, "hot sauce": 0.65, "worcestershire sauce": 0.7,
        "beef": 0.8, "chicken": 0.75, "pork": 0.7,
        "corn": 0.65, "potato": 0.7, "eggs": 0.65,
        "flour": 0.6, "milk": 0.6, "vegetable oil": 0.6,
        "beer": 0.6, "honey": 0.55, "cumin": 0.5,
    },
    "British": {
        "butter": 0.85, "cream": 0.75, "thyme": 0.8,
        "rosemary": 0.8, "parsley": 0.7, "bay leaf": 0.75,
        "lamb": 0.85, "pork": 0.75, "beef": 0.8, "bacon": 0.75,
        "potato": 0.85, "carrot": 0.8, "celery": 0.75,
        "onion": 0.8, "mushroom": 0.65, "leek": 0.75,
        "beer": 0.65, "worcestershire sauce": 0.7, "dijon mustard": 0.6,
        "cheddar": 0.7, "eggs": 0.65, "flour": 0.65, "milk": 0.6,
        "beef stock": 0.75, "chicken stock": 0.7,
    },
}


# ---------------------------------------------------------------------------
# Score derivation
# ---------------------------------------------------------------------------

def pair_score(a: str, b: str, affinities: dict[str, float]) -> float | None:
    sa = affinities.get(a, 0.0)
    sb = affinities.get(b, 0.0)
    if sa == 0.0 and sb == 0.0:
        return None
    base = math.sqrt(sa * sb) if sa > 0 and sb > 0 else (sa + sb) * 0.3
    noise = random.uniform(-0.04, 0.04)
    return round(min(max(base + noise, 0.0), 1.0), 4)


def global_affinity(ingredient: str) -> float:
    scores = [aff.get(ingredient, 0.0) for aff in CUISINE_AFFINITIES.values()]
    present = [s for s in scores if s > 0]
    return sum(present) / len(present) if present else 0.05


def global_pair_score(a: str, b: str) -> float | None:
    sa = global_affinity(a)
    sb = global_affinity(b)
    base = math.sqrt(sa * sb)
    noise = random.uniform(-0.03, 0.03)
    score = round(min(max(base + noise, 0.0), 1.0), 4)
    return score if score > 0.05 else None


TOP_N = 50
MIN_GLOBAL_SCORE = 0.08
MIN_CUISINE_SCORE = 0.12


def generate(output_path: str) -> None:
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

    sorted_ings = sorted(INGREDIENTS)
    cur.executemany(
        "INSERT INTO ingredients (name, freq) VALUES (?, ?)",
        [(name, random.randint(500, 50000)) for name in sorted_ings],
    )
    ing_id = {
        name: row[0]
        for name, row in zip(
            sorted_ings,
            cur.execute("SELECT id FROM ingredients ORDER BY id").fetchall(),
        )
    }

    cuisine_names = ["all"] + sorted(CUISINE_AFFINITIES.keys())
    cur.executemany(
        "INSERT INTO cuisines (name, recipe_count) VALUES (?, ?)",
        [(c, random.randint(5000, 200000)) for c in cuisine_names],
    )
    cuisine_id = {
        name: row[0]
        for name, row in zip(
            cuisine_names,
            cur.execute("SELECT id FROM cuisines ORDER BY id").fetchall(),
        )
    }

    def insert_pairs(pairs_with_scores, cid):
        # Group by ingredient_a, keep top N by score
        from itertools import groupby
        rows = sorted(pairs_with_scores, key=lambda r: (r[0], -r[2]))
        kept = []
        for a_id, group in groupby(rows, key=lambda r: r[0]):
            kept.extend(list(group)[:TOP_N])
        cur.executemany(
            "INSERT OR IGNORE INTO pairings VALUES (?, ?, ?, ?, ?)", kept
        )

    # Global pairings
    global_pairs = []
    for a, b in combinations(sorted_ings, 2):
        score = global_pair_score(a, b)
        if score is None or score < MIN_GLOBAL_SCORE:
            continue
        cooc = int(score * 5000 * random.uniform(0.5, 1.5))
        global_pairs.append((ing_id[a], ing_id[b], cuisine_id["all"], score, cooc))
        global_pairs.append((ing_id[b], ing_id[a], cuisine_id["all"], score, cooc))
    insert_pairs(global_pairs, cuisine_id["all"])

    # Per-cuisine pairings
    for cuisine, affinities in CUISINE_AFFINITIES.items():
        cid = cuisine_id[cuisine]
        pairs = []
        for a, b in combinations(sorted_ings, 2):
            score = pair_score(a, b, affinities)
            if score is None or score < MIN_CUISINE_SCORE:
                continue
            cooc = int(score * 1000 * random.uniform(0.5, 1.5))
            pairs.append((ing_id[a], ing_id[b], cid, score, cooc))
            pairs.append((ing_id[b], ing_id[a], cid, score, cooc))
        insert_pairs(pairs, cid)

    con.commit()
    con.close()

    size_kb = db_path.stat().st_size / 1024
    rows = sqlite3.connect(db_path).execute("SELECT COUNT(*) FROM pairings").fetchone()[0]
    print(f"Demo DB → {output_path}")
    print(f"  Ingredients : {len(INGREDIENTS)}")
    print(f"  Cuisines    : {len(cuisine_names)}")
    print(f"  Pairing rows: {rows:,}")
    print(f"  File size   : {size_kb:.0f} KB")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="../web/public/pairings.db")
    args = parser.parse_args()
    generate(args.output)
