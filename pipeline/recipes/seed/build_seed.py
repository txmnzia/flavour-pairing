#!/usr/bin/env python3
"""
Generate the committed starter corpus seed_recipes.jsonl (issue #56).

This is a curated bootstrap of well-known dishes, hand-written against the app's
canonical ingredient vocabulary, used until a full external corpus (RecipeNLG /
a French dump) can be ingested through the same pipeline (see the adapters in
pipeline/recipes/adapters/). Source links point at each dish's Wikipedia article
-- a stable, real description of the dish. Regenerate with:

    python3 pipeline/recipes/seed/build_seed.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "seed_recipes.jsonl")
WIKI_EN = "https://en.wikipedia.org/wiki/"
WIKI_FR = "https://fr.wikipedia.org/wiki/"

# (title, lang, wikipedia_slug, [ingredient phrases])
DISHES = [
    # --- Italian / tomato-basil-mozzarella cluster ---
    ("Pizza Margherita", "en", "Pizza_Margherita",
     ["tomato", "mozzarella", "basil", "olive oil", "wheat", "yeast"]),
    ("Caprese salad", "en", "Caprese_salad",
     ["tomato", "mozzarella", "basil", "olive oil", "black pepper"]),
    ("Bruschetta", "en", "Bruschetta",
     ["tomato", "basil", "garlic", "olive oil", "bread"]),
    ("Pasta al pomodoro", "en", "Pasta_al_pomodoro",
     ["pasta", "tomato", "garlic", "basil", "olive oil", "onion"]),
    ("Spaghetti alla carbonara", "en", "Carbonara",
     ["pasta", "egg", "bacon", "parmesan", "black pepper"]),
    ("Spaghetti aglio e olio", "en", "Aglio_e_olio",
     ["pasta", "garlic", "olive oil", "chili pepper", "parsley"]),
    ("Pesto alla genovese", "en", "Pesto",
     ["basil", "garlic", "olive oil", "pine nut", "parmesan"]),
    ("Lasagne", "en", "Lasagne",
     ["pasta", "tomato", "beef", "onion", "mozzarella", "parmesan", "carrot"]),
    ("Risotto alla milanese", "en", "Risotto",
     ["rice", "onion", "white wine", "parmesan", "butter", "saffron"]),
    ("Minestrone", "en", "Minestrone",
     ["tomato", "carrot", "celery", "onion", "bean", "pasta", "zucchini"]),
    ("Eggplant parmesan", "en", "Parmigiana",
     ["eggplant", "tomato", "mozzarella", "parmesan", "basil", "olive oil"]),
    ("Tiramisu", "en", "Tiramisu",
     ["coffee", "egg", "sugar", "cocoa", "mascarpone cheese"]),
    # --- French classics ---
    ("Duck à l'orange", "en", "Duck_à_l%27orange",
     ["duck", "orange", "butter", "sugar", "shallot", "white wine"]),
    ("Coq au vin", "en", "Coq_au_vin",
     ["chicken", "red wine", "mushroom", "bacon", "onion", "garlic", "thyme"]),
    ("Bœuf bourguignon", "en", "Beef_bourguignon",
     ["beef", "red wine", "carrot", "onion", "mushroom", "bacon", "garlic"]),
    ("Blanquette de veau", "en", "Blanquette_de_veau",
     ["veal", "mushroom", "carrot", "onion", "cream", "egg"]),
    ("Ratatouille", "en", "Ratatouille",
     ["eggplant", "zucchini", "tomato", "bell pepper", "onion", "garlic", "olive oil"]),
    ("French onion soup", "en", "French_onion_soup",
     ["onion", "butter", "beef", "bread", "gruyere", "thyme"]),
    ("Quiche Lorraine", "en", "Quiche_Lorraine",
     ["egg", "cream", "bacon", "butter", "nutmeg"]),
    ("Salade niçoise", "en", "Salade_niçoise",
     ["tuna", "tomato", "egg", "olive", "green bean", "anchovy", "olive oil"]),
    ("Bouillabaisse", "en", "Bouillabaisse",
     ["fish", "tomato", "fennel", "garlic", "onion", "saffron", "olive oil"]),
    ("Moules marinière", "en", "Moules_marinières",
     ["mussel", "shallot", "white wine", "butter", "parsley", "garlic"]),
    ("Béarnaise sauce", "en", "Béarnaise_sauce",
     ["butter", "egg", "shallot", "tarragon", "vinegar", "black pepper"]),
    ("Vichyssoise", "en", "Vichyssoise",
     ["leek", "potato", "cream", "onion", "butter"]),
    ("Tarte Tatin", "en", "Tarte_Tatin",
     ["apple", "sugar", "butter"]),
    ("Crème brûlée", "en", "Crème_brûlée",
     ["cream", "egg", "sugar", "vanilla"]),
    ("Ratatouille niçoise", "fr", "Ratatouille",
     ["aubergine", "courgette", "tomate", "poivron", "oignon", "ail", "huile d'olive"]),
    ("Bœuf bourguignon", "fr", "Bœuf_bourguignon",
     ["bœuf", "vin rouge", "carotte", "oignon", "champignon", "lardon", "ail"]),
    ("Coq au vin", "fr", "Coq_au_vin",
     ["poulet", "vin rouge", "champignon", "lardon", "oignon", "ail", "thym"]),
    ("Blanquette de veau", "fr", "Blanquette_de_veau",
     ["veau", "champignon", "carotte", "oignon", "crème", "œuf"]),
    ("Soupe à l'oignon", "fr", "Soupe_à_l%27oignon",
     ["oignon", "beurre", "bœuf", "pain", "gruyère", "thym"]),
    ("Canard à l'orange", "fr", "Canard_à_l%27orange",
     ["canard", "orange", "beurre", "sucre", "échalote", "vin blanc"]),
    ("Quiche lorraine", "fr", "Quiche_lorraine",
     ["œuf", "crème", "lardon", "beurre", "muscade"]),
    ("Moules marinières", "fr", "Moules_marinières",
     ["moule", "échalote", "vin blanc", "beurre", "persil", "ail"]),
    ("Tarte Tatin", "fr", "Tarte_Tatin",
     ["pomme", "sucre", "beurre"]),
    ("Salade niçoise", "fr", "Salade_niçoise",
     ["thon", "tomate", "œuf", "olive", "haricot vert", "anchois"]),
    ("Bouillabaisse", "fr", "Bouillabaisse",
     ["poisson", "tomate", "fenouil", "ail", "oignon", "safran"]),
    ("Poulet basquaise", "fr", "Poulet_basquaise",
     ["poulet", "poivron", "tomate", "oignon", "ail", "jambon"]),
    ("Bœuf carottes", "fr", "Bœuf_carottes",
     ["bœuf", "carotte", "oignon", "vin blanc", "thym"]),
    ("Gratin dauphinois", "fr", "Gratin_dauphinois",
     ["pomme de terre", "crème", "lait", "ail", "muscade"]),
    # --- Other cuisines, broad ingredient coverage ---
    ("Guacamole", "en", "Guacamole",
     ["avocado", "lime", "onion", "coriander", "tomato", "chili pepper"]),
    ("Hummus", "en", "Hummus",
     ["chickpea", "garlic", "lemon", "olive oil", "cumin"]),
    ("Pad thai", "en", "Pad_thai",
     ["rice noodle", "shrimp", "egg", "peanut", "lime", "garlic", "bean sprout"]),
    ("Chicken tikka masala", "en", "Chicken_tikka_masala",
     ["chicken", "tomato", "yogurt", "garlic", "ginger", "cumin", "coriander"]),
    ("Fish and chips", "en", "Fish_and_chips",
     ["fish", "potato", "vinegar"]),
    ("Shepherd's pie", "en", "Shepherd%27s_pie",
     ["lamb", "potato", "onion", "carrot", "pea", "butter"]),
    ("Caesar salad", "en", "Caesar_salad",
     ["lettuce", "parmesan", "garlic", "anchovy", "lemon", "egg", "bread"]),
    ("Greek salad", "en", "Greek_salad",
     ["tomato", "cucumber", "onion", "olive", "feta", "olive oil"]),
    ("Paella", "en", "Paella",
     ["rice", "shrimp", "mussel", "chicken", "bell pepper", "saffron", "garlic"]),
    ("Gazpacho", "en", "Gazpacho",
     ["tomato", "cucumber", "bell pepper", "garlic", "olive oil", "vinegar"]),
    ("Beef stew", "en", "Beef_bourguignon",
     ["beef", "potato", "carrot", "onion", "celery", "thyme"]),
    ("Chocolate chip cookie", "en", "Chocolate_chip_cookie",
     ["chocolate", "butter", "sugar", "egg", "vanilla"]),
    ("Apple pie", "en", "Apple_pie",
     ["apple", "sugar", "butter", "cinnamon", "nutmeg"]),
    ("Banana bread", "en", "Banana_bread",
     ["banana", "sugar", "butter", "egg", "walnut", "cinnamon"]),
    ("Carrot cake", "en", "Carrot_cake",
     ["carrot", "sugar", "egg", "walnut", "cinnamon", "cream cheese"]),
    ("Omelette", "en", "Omelette",
     ["egg", "butter", "cheese", "chive"]),
    ("Pancakes", "en", "Pancake",
     ["egg", "milk", "sugar", "butter"]),
    ("Miso soup", "en", "Miso_soup",
     ["miso", "tofu", "seaweed", "green onion"]),
    ("Chili con carne", "en", "Chili_con_carne",
     ["beef", "bean", "tomato", "onion", "garlic", "cumin", "chili pepper"]),
    ("Roast chicken", "en", "Roast_chicken",
     ["chicken", "butter", "lemon", "thyme", "garlic", "rosemary"]),
    ("Grilled salmon", "en", "Salmon_as_food",
     ["salmon", "lemon", "dill", "butter", "garlic"]),
]


def main():
    with open(OUT, "w", encoding="utf-8") as f:
        for i, (title, lang, slug, ings) in enumerate(DISHES):
            url = (WIKI_FR if lang == "fr" else WIKI_EN) + slug
            rec = {"id": f"seed-{i}", "title": title, "lang": lang,
                   "ingredients": ings, "url": url, "source": "seed"}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"Wrote {len(DISHES)} seed recipes to {OUT}")


if __name__ == "__main__":
    main()
