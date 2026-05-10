#!/usr/bin/env python3
"""
Rebuild pairings.json using the curated ingredients.txt allowlist.

Usage:
    python apply_ingredients.py

Reads:
    pipeline/ingredients.txt        - curated ingredient names (one per line, # comments)
    feature/real-data pairings.json - source pairing data

Writes:
    /tmp/pairings_curated.json      - filtered output (push this to feature/real-data)
"""

import json
import subprocess
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INGREDIENTS_FILE = os.path.join(SCRIPT_DIR, "ingredients.txt")


def load_allowlist(path: str) -> set[str]:
    allowed = set()
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                allowed.add(line)
    return allowed


def load_pairings_json() -> dict:
    result = subprocess.run(
        ["git", "show", "origin/feature/real-data:web/public/pairings.json"],
        capture_output=True, text=True, cwd=SCRIPT_DIR
    )
    if result.returncode != 0:
        sys.exit(f"Failed to read pairings.json from feature/real-data:\n{result.stderr}")
    return json.loads(result.stdout)


def main():
    print("Loading allowlist…")
    allowed = load_allowlist(INGREDIENTS_FILE)
    print(f"  {len(allowed)} ingredients in allowlist")

    print("Loading pairings.json from feature/real-data…")
    data = load_pairings_json()

    old_ingredients = data["i"]
    cuisines = data["c"]
    old_pairings = data["p"]

    print(f"  Source: {len(old_ingredients)} ingredients, {len(old_pairings)} pairing entries")

    # Build index mapping: old_idx -> new_idx (or None if removed)
    new_ingredients = [name for name in old_ingredients if name in allowed]
    old_to_new = {}
    new_idx = 0
    for old_idx, name in enumerate(old_ingredients):
        if name in allowed:
            old_to_new[old_idx] = new_idx
            new_idx += 1
        else:
            old_to_new[old_idx] = None

    removed_count = len(old_ingredients) - len(new_ingredients)
    print(f"  Removing {removed_count} ingredients not in allowlist")

    # Rebuild pairings: filter keys and neighbor lists
    new_pairings = {}
    for key, neighbors in old_pairings.items():
        parts = key.split(",")
        cuisine_idx = int(parts[0])
        old_ing_idx = int(parts[1])

        new_ing_idx = old_to_new.get(old_ing_idx)
        if new_ing_idx is None:
            continue  # ingredient was removed

        new_neighbors = []
        for other_old_idx, score in neighbors:
            other_new_idx = old_to_new.get(other_old_idx)
            if other_new_idx is not None:
                new_neighbors.append([other_new_idx, score])

        if new_neighbors:
            new_key = f"{cuisine_idx},{new_ing_idx}"
            if new_key in new_pairings:
                # merge (take max score per neighbor)
                existing = {idx: sc for idx, sc in new_pairings[new_key]}
                for idx, sc in new_neighbors:
                    existing[idx] = max(existing.get(idx, 0), sc)
                new_pairings[new_key] = [[idx, sc] for idx, sc in sorted(existing.items())]
            else:
                new_pairings[new_key] = sorted(new_neighbors, key=lambda x: -x[1])

    output = {"v": 1, "i": new_ingredients, "c": cuisines, "p": new_pairings}

    out_path = "/tmp/pairings_curated.json"
    with open(out_path, "w") as f:
        json.dump(output, f, separators=(",", ":"))

    size_mb = os.path.getsize(out_path) / 1_000_000
    print(f"\nDone. Output: {out_path}")
    print(f"  {len(new_ingredients)} ingredients, {len(new_pairings)} pairing entries, {size_mb:.1f} MB")
    print(f"\nNext step: ask Claude to push /tmp/pairings_curated.json to feature/real-data")


if __name__ == "__main__":
    main()
