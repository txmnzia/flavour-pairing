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


# ---------------------------------------------------------------------------
# Recipe catalogue — titles + ingredient names (must match INGREDIENTS list)
# ---------------------------------------------------------------------------

RECIPES = [
    # Italian
    ("Spaghetti Carbonara", ["pasta", "bacon", "eggs", "parmesan", "black pepper", "olive oil"]),
    ("Spaghetti Bolognese", ["pasta", "beef", "tomato", "onion", "garlic", "red wine", "olive oil", "parmesan"]),
    ("Chicken Parmigiana", ["chicken", "tomato", "mozzarella", "parmesan", "breadcrumbs", "olive oil", "garlic", "basil"]),
    ("Margherita Pizza", ["tomato", "mozzarella", "basil", "olive oil"]),
    ("Mushroom Risotto", ["rice", "mushroom", "shallot", "white wine", "parmesan", "butter", "chicken stock"]),
    ("Pesto Pasta", ["pasta", "basil", "pine nuts", "parmesan", "garlic", "olive oil"]),
    ("Arrabbiata Pasta", ["pasta", "tomato", "garlic", "cayenne", "olive oil", "parsley"]),
    ("Bruschetta", ["bread", "tomato", "garlic", "basil", "olive oil"]),
    ("Osso Buco", ["beef", "onion", "carrot", "celery", "white wine", "tomato", "lemon", "garlic", "butter"]),
    ("Eggplant Parmigiana", ["eggplant", "tomato", "mozzarella", "parmesan", "basil", "olive oil", "garlic"]),
    ("Gnocchi al Pesto", ["potato", "flour", "eggs", "basil", "pine nuts", "parmesan", "garlic", "olive oil"]),
    ("Pasta Cacio e Pepe", ["pasta", "parmesan", "black pepper", "butter"]),
    ("Chicken Cacciatore", ["chicken", "tomato", "olive oil", "garlic", "onion", "bell pepper", "mushroom", "olives", "rosemary"]),
    ("Fettuccine Alfredo", ["pasta", "butter", "parmesan", "cream", "black pepper"]),
    ("Shrimp Scampi", ["shrimp", "garlic", "white wine", "butter", "lemon", "parsley", "pasta"]),
    ("Caprese Salad", ["tomato", "mozzarella", "basil", "olive oil", "balsamic vinegar"]),
    ("Panzanella", ["tomato", "bread", "basil", "red wine", "olive oil", "capers", "olives"]),
    ("Asparagus Risotto", ["rice", "asparagus", "shallot", "white wine", "parmesan", "butter", "chicken stock"]),
    # French
    ("Boeuf Bourguignon", ["beef", "red wine", "onion", "carrot", "garlic", "mushroom", "bacon", "thyme", "bay leaf"]),
    ("Coq au Vin", ["chicken", "red wine", "bacon", "mushroom", "onion", "garlic", "thyme", "butter"]),
    ("French Onion Soup", ["onion", "butter", "white wine", "beef stock", "thyme", "bread", "gruyere"]),
    ("Ratatouille", ["tomato", "eggplant", "zucchini", "bell pepper", "onion", "garlic", "thyme", "olive oil", "basil"]),
    ("Quiche Lorraine", ["bacon", "eggs", "cream", "gruyere", "flour", "butter", "thyme"]),
    ("Salmon en Papillote", ["salmon", "lemon", "thyme", "butter", "shallot"]),
    ("Duck Confit", ["duck", "garlic", "thyme", "shallot", "black pepper"]),
    ("Nicoise Salad", ["tuna", "tomato", "eggs", "olives", "anchovies", "lemon", "olive oil"]),
    ("Vichyssoise", ["leek", "potato", "cream", "chicken stock", "onion", "butter"]),
    ("Bouillabaisse", ["salmon", "shrimp", "tomato", "onion", "garlic", "saffron", "white wine", "olive oil", "thyme"]),
    ("Beef Tartare", ["beef", "shallot", "capers", "dijon mustard", "parsley", "eggs"]),
    ("Croque Monsieur", ["bread", "butter", "gruyere", "dijon mustard"]),
    ("Duck Breast with Red Wine", ["duck", "shallot", "thyme", "garlic", "red wine", "black pepper", "butter"]),
    ("Potato Gratin", ["potato", "cream", "gruyere", "garlic", "thyme", "butter"]),
    ("Poached Salmon", ["salmon", "shallot", "white wine", "lemon", "thyme", "butter"]),
    ("French Lentils", ["lentils", "carrot", "onion", "celery", "garlic", "thyme", "dijon mustard"]),
    # Indian
    ("Chicken Tikka Masala", ["chicken", "tomato", "cream", "garlic", "ginger", "cumin", "coriander", "turmeric", "paprika", "cayenne"]),
    ("Butter Chicken", ["chicken", "tomato", "cream", "butter", "garlic", "ginger", "cumin", "coriander", "turmeric", "cardamom"]),
    ("Palak Paneer", ["spinach", "tomato", "onion", "garlic", "ginger", "cumin", "coriander", "turmeric", "cream"]),
    ("Dal Makhani", ["lentils", "tomato", "onion", "garlic", "ginger", "cumin", "coriander", "cream", "butter"]),
    ("Chana Masala", ["chickpeas", "tomato", "onion", "garlic", "ginger", "cumin", "coriander", "turmeric", "cayenne"]),
    ("Lamb Rogan Josh", ["lamb", "tomato", "onion", "garlic", "ginger", "cumin", "coriander", "cardamom", "cinnamon", "cayenne"]),
    ("Aloo Gobi", ["potato", "cauliflower", "onion", "garlic", "ginger", "cumin", "coriander", "turmeric"]),
    ("Biryani", ["rice", "chicken", "onion", "garlic", "ginger", "cardamom", "cinnamon", "saffron", "cumin", "coriander"]),
    ("Tandoori Chicken", ["chicken", "garlic", "ginger", "cumin", "coriander", "turmeric", "cayenne", "paprika"]),
    ("Saag Aloo", ["spinach", "potato", "onion", "garlic", "ginger", "cumin", "turmeric"]),
    ("Lamb Tagine", ["lamb", "onion", "garlic", "ginger", "cumin", "coriander", "cinnamon", "saffron", "tomato"]),
    ("Moroccan Chicken", ["chicken", "onion", "garlic", "ginger", "cumin", "coriander", "cinnamon", "saffron", "tomato", "olive oil"]),
    ("Cauliflower Curry", ["cauliflower", "onion", "garlic", "ginger", "tomato", "cumin", "coriander", "turmeric", "coconut oil"]),
    # Asian
    ("Pad Thai", ["rice", "shrimp", "eggs", "scallion", "lime", "fish sauce", "garlic", "soy sauce"]),
    ("Chicken Fried Rice", ["rice", "chicken", "eggs", "soy sauce", "sesame oil", "scallion", "garlic", "ginger"]),
    ("Teriyaki Chicken", ["chicken", "soy sauce", "garlic", "ginger", "sesame seeds", "scallion"]),
    ("Korean Bulgogi", ["beef", "soy sauce", "sesame oil", "garlic", "ginger", "scallion", "sesame seeds", "sugar"]),
    ("Thai Green Curry", ["chicken", "coconut oil", "garlic", "ginger", "fish sauce", "lime", "basil"]),
    ("Beef and Broccoli", ["beef", "broccoli", "soy sauce", "sesame oil", "garlic", "ginger", "scallion", "sesame seeds"]),
    ("Egg Fried Rice", ["rice", "eggs", "soy sauce", "sesame oil", "scallion", "garlic", "ginger"]),
    ("Szechuan Tofu", ["tofu", "soy sauce", "sesame oil", "garlic", "ginger", "scallion", "cayenne"]),
    ("Salmon Teriyaki", ["salmon", "soy sauce", "garlic", "ginger", "sesame seeds", "scallion"]),
    ("Pork Belly with Soy", ["pork", "soy sauce", "garlic", "ginger", "honey", "sesame seeds", "scallion"]),
    # Mediterranean/Greek
    ("Greek Salad", ["tomato", "cucumber", "feta", "olives", "red wine", "olive oil", "oregano"]),
    ("Lamb Souvlaki", ["lamb", "lemon", "garlic", "oregano", "olive oil", "thyme"]),
    ("Spanakopita", ["spinach", "feta", "eggs", "onion", "olive oil"]),
    ("Moussaka", ["eggplant", "beef", "tomato", "onion", "garlic", "cinnamon", "parmesan", "milk", "butter", "flour"]),
    ("Shakshuka", ["tomato", "bell pepper", "onion", "garlic", "cumin", "paprika", "cayenne", "eggs", "olive oil"]),
    ("Falafel", ["chickpeas", "onion", "garlic", "cumin", "coriander", "parsley", "cayenne"]),
    ("Tabbouleh", ["parsley", "tomato", "lemon", "olive oil", "mint"]),
    ("Chickpea Stew", ["chickpeas", "tomato", "onion", "garlic", "cumin", "paprika", "olive oil", "spinach"]),
    ("Gazpacho", ["tomato", "cucumber", "bell pepper", "onion", "garlic", "olive oil", "white wine vinegar"]),
    # Mexican
    ("Chicken Tacos", ["chicken", "cumin", "coriander", "cayenne", "garlic", "lime", "cilantro", "onion"]),
    ("Beef Tacos", ["beef", "cumin", "coriander", "cayenne", "garlic", "lime", "cilantro", "onion"]),
    ("Guacamole", ["avocado", "lime", "cilantro", "onion", "garlic"]),
    ("Chicken Enchiladas", ["chicken", "tomato", "onion", "garlic", "cumin", "cayenne", "cheddar", "cilantro"]),
    ("Pork Carnitas", ["pork", "cumin", "coriander", "garlic", "lime", "onion", "oregano"]),
    ("Chili con Carne", ["beef", "black beans", "tomato", "onion", "garlic", "cumin", "cayenne", "paprika"]),
    ("Black Bean Soup", ["black beans", "onion", "garlic", "cumin", "cayenne", "tomato", "lime", "cilantro"]),
    ("Corn Salsa", ["corn", "tomato", "lime", "cilantro", "onion", "garlic"]),
    # American / British
    ("Beef Burger", ["beef", "onion", "cheddar", "garlic", "black pepper"]),
    ("Mac and Cheese", ["pasta", "cheddar", "milk", "butter", "flour", "black pepper"]),
    ("BBQ Pulled Pork", ["pork", "paprika", "cumin", "garlic", "onion", "cayenne", "honey", "apple cider vinegar"]),
    ("Chicken Wings", ["chicken", "cayenne", "paprika", "garlic", "butter", "hot sauce"]),
    ("Caesar Salad", ["parmesan", "anchovies", "lemon", "garlic", "olive oil", "black pepper", "eggs"]),
    ("Corn Chowder", ["corn", "potato", "onion", "celery", "cream", "butter", "thyme"]),
    ("Shepherd's Pie", ["lamb", "carrot", "onion", "potato", "peas", "thyme", "rosemary", "beef stock", "butter"]),
    ("Beef Stew", ["beef", "carrot", "potato", "onion", "celery", "thyme", "bay leaf", "beef stock", "red wine"]),
    ("Fish and Chips", ["cod", "flour", "beer", "vegetable oil"]),
    ("Chicken Pot Pie", ["chicken", "carrot", "potato", "peas", "onion", "celery", "cream", "butter", "flour", "thyme"]),
    # Global
    ("Roast Chicken", ["chicken", "garlic", "thyme", "rosemary", "lemon", "butter", "onion"]),
    ("Lamb Chops", ["lamb", "rosemary", "garlic", "lemon", "olive oil", "thyme"]),
    ("Salmon with Lemon Butter", ["salmon", "lemon", "butter", "garlic", "thyme", "parsley"]),
    ("Grilled Shrimp", ["shrimp", "garlic", "lemon", "olive oil", "parsley", "cayenne"]),
    ("Stuffed Bell Peppers", ["bell pepper", "beef", "rice", "tomato", "onion", "garlic", "parmesan", "oregano"]),
    ("Lentil Soup", ["lentils", "carrot", "onion", "celery", "garlic", "cumin", "coriander", "olive oil", "tomato"]),
    ("Roasted Vegetables", ["carrot", "zucchini", "eggplant", "bell pepper", "onion", "garlic", "olive oil", "thyme"]),
    ("Tuna Nicoise", ["tuna", "tomato", "eggs", "olives", "lemon", "olive oil", "anchovies"]),
    ("Potato Soup", ["potato", "onion", "garlic", "cream", "butter", "chive", "chicken stock"]),
    ("Spinach and Feta Omelette", ["eggs", "spinach", "feta", "garlic", "olive oil"]),
    ("Chicken Soup", ["chicken", "carrot", "onion", "celery", "thyme", "bay leaf", "chicken stock", "parsley"]),
    ("Minestrone", ["tomato", "carrot", "onion", "celery", "garlic", "olive oil", "thyme", "lentils"]),
    ("Pasta Primavera", ["pasta", "zucchini", "tomato", "bell pepper", "garlic", "olive oil", "parmesan", "basil"]),
    ("Braised Short Ribs", ["beef", "red wine", "onion", "carrot", "celery", "garlic", "thyme", "rosemary", "tomato"]),
    ("Pot Roast", ["beef", "carrot", "potato", "onion", "celery", "garlic", "thyme", "rosemary", "beef stock"]),
    ("Avocado Salad", ["avocado", "tomato", "lime", "cilantro", "onion"]),
]

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


def export_json(db_path: Path, json_path: str) -> None:
    """Export the SQLite DB to the compact JSON format consumed by the web app."""
    con = sqlite3.connect(db_path)

    ing_rows = con.execute("SELECT id, name FROM ingredients ORDER BY id").fetchall()
    ingredients = [name for _, name in ing_rows]
    sql_ing_to_idx = {sql_id: idx for idx, (sql_id, _) in enumerate(ing_rows)}

    # Cuisines: "all" must be at index 0
    cuis_rows = con.execute("SELECT id, name FROM cuisines ORDER BY id").fetchall()
    cuis_rows.sort(key=lambda r: (r[1] != "all", r[1]))
    cuisines = [name for _, name in cuis_rows]
    sql_cuis_to_idx = {sql_id: idx for idx, (sql_id, _) in enumerate(cuis_rows)}

    pairings: dict[str, list] = {}
    for a_id, b_id, c_id, npmi in con.execute(
        "SELECT ingredient_a, ingredient_b, cuisine_id, npmi FROM pairings"
        " ORDER BY cuisine_id, ingredient_a, npmi DESC"
    ).fetchall():
        key = f"{sql_cuis_to_idx[c_id]},{sql_ing_to_idx[a_id]}"
        pairings.setdefault(key, []).append([sql_ing_to_idx[b_id], round(npmi * 100)])

    data = {"v": 1, "i": ingredients, "c": cuisines, "p": pairings}

    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    import json as _json
    with open(out, "w") as f:
        _json.dump(data, f, separators=(",", ":"))

    size_kb = out.stat().st_size / 1024
    print(f"  JSON → {json_path} ({size_kb:.0f} KB, {len(pairings)} pairing groups)")
    con.close()


def export_recipes_json(json_path: str, recipes: list, db_path: Path) -> None:
    """Export recipe catalogue to a standalone JSON file (separate from pairings)."""
    import json as _json
    con = sqlite3.connect(db_path)
    valid_names = {name for (name,) in con.execute("SELECT name FROM ingredients").fetchall()}
    con.close()

    recipe_data = []
    for title, ing_list in recipes:
        valid_ings = [n for n in ing_list if n in valid_names]
        if len(valid_ings) >= 2:
            recipe_data.append([title, valid_ings])

    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        _json.dump({"v": 1, "r": recipe_data}, f, separators=(",", ":"))

    size_kb = out.stat().st_size / 1024
    print(f"  Recipes JSON → {json_path} ({len(recipe_data)} recipes, {size_kb:.0f} KB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="../web/public/pairings.db")
    parser.add_argument("--json-output", default="../web/public/pairings.json")
    parser.add_argument("--recipes-output", default="../web/public/recipes.json")
    args = parser.parse_args()
    generate(args.output)
    export_json(Path(args.output), args.json_output)
    export_recipes_json(args.recipes_output, RECIPES, Path(args.output))
