"""
Convert FlavorGraph data (nodes + edges CSVs) into pairings.json.

Sources (Apache 2.0):
  nodes: https://raw.githubusercontent.com/lamypark/FlavorGraph/master/input/nodes_191120.csv
  edges: https://raw.githubusercontent.com/lamypark/FlavorGraph/master/input/edges_191120.csv

Usage:
  python pipeline/flavorgraph_import.py --output web/public/pairings.json
"""

import argparse
import csv
import json
import sys
import urllib.request
from collections import defaultdict

NODES_URL = "https://raw.githubusercontent.com/lamypark/FlavorGraph/master/input/nodes_191120.csv"
EDGES_URL = "https://raw.githubusercontent.com/lamypark/FlavorGraph/master/input/edges_191120.csv"

# All pairs with score ≥ MIN_SCORE are kept — no top-N cap (see pipeline/DATA.md invariant 3).
MIN_SCORE = 0.01


def fetch_csv(url: str) -> list[dict]:
    print(f"Fetching {url} …", flush=True)
    with urllib.request.urlopen(url) as r:
        lines = r.read().decode("utf-8").splitlines()
    return list(csv.DictReader(lines))


def normalise_name(raw: str) -> str:
    return raw.replace("_", " ").strip().lower()


def main(output: str) -> None:
    nodes_rows = fetch_csv(NODES_URL)
    edges_rows = fetch_csv(EDGES_URL)

    # Build ingredient set: node_id (int) → normalised name
    ingr_by_id: dict[int, str] = {}
    for row in nodes_rows:
        if row["node_type"] == "ingredient":
            ingr_by_id[int(row["node_id"])] = normalise_name(row["name"])

    print(f"  {len(ingr_by_id)} ingredient nodes", flush=True)

    # Collect ingr-ingr edges
    raw_pairs: dict[int, list[tuple[int, float]]] = defaultdict(list)
    skipped = 0
    for row in edges_rows:
        if row["edge_type"] != "ingr-ingr":
            continue
        a, b = int(row["id_1"]), int(row["id_2"])
        if a not in ingr_by_id or b not in ingr_by_id:
            skipped += 1
            continue
        score = float(row["score"])
        if score < MIN_SCORE:
            continue
        raw_pairs[a].append((b, score))
        raw_pairs[b].append((a, score))

    print(f"  {sum(len(v) for v in raw_pairs.values()) // 2} ingr-ingr edges loaded ({skipped} skipped)", flush=True)

    # Only keep ingredients that actually have pairings
    active_ids = sorted(id_ for id_ in ingr_by_id if id_ in raw_pairs)
    name_list = [ingr_by_id[id_] for id_ in active_ids]
    old_to_new = {old: new for new, old in enumerate(active_ids)}

    print(f"  {len(active_ids)} ingredients with at least one pairing", flush=True)

    # Build pairings dict: "ingredientIdx" → [[pairedIdx, score*100], …] (all pairs, score-sorted)
    pairings: dict[str, list[list[int]]] = {}
    for old_id in active_ids:
        new_id = old_to_new[old_id]
        candidates = raw_pairs[old_id]
        # Remap to new indices
        remapped = [
            (old_to_new[b], s)
            for b, s in candidates
            if b in old_to_new
        ]
        remapped.sort(key=lambda x: x[1], reverse=True)
        if remapped:
            pairings[str(new_id)] = [[b, round(s * 100)] for b, s in remapped]

    out = {
        "v": 2,
        "meta": {
            "source": "flavorgraph",
            "ingredients": len(name_list),
        },
        "i": name_list,
        "p": pairings,
    }

    with open(output, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = len(json.dumps(out, separators=(",", ":"))) / 1024
    print(f"Written {output}  ({len(name_list)} ingredients, {len(pairings)} with pairings, {size_kb:.0f} KB)", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="web/public/pairings.json")
    args = parser.parse_args()
    main(args.output)
