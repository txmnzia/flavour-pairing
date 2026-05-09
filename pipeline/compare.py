#!/usr/bin/env python3
"""
Compare two pairings.json files to understand how dataset size affects results.

Usage:
    python compare.py /tmp/pairings_500k.json /tmp/pairings_full.json

    # Optional: focus on specific ingredients
    python compare.py /tmp/pairings_500k.json /tmp/pairings_full.json \\
        --ingredients garlic butter salmon tomato
"""

import argparse
import json
from pathlib import Path


PROBE_INGREDIENTS = [
    "garlic", "butter", "olive oil", "onion", "thyme",
    "tomato", "cream", "lemon", "chicken", "salmon",
]


def load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def cuisine_idx(data: dict, name: str) -> int | None:
    try:
        return data["c"].index(name)
    except ValueError:
        return None


def get_pairings(data: dict, ingredient: str, cuisine: str = "all") -> list[tuple[str, float]]:
    try:
        ing_idx  = data["i"].index(ingredient)
        cuis_idx = cuisine_idx(data, cuisine)
    except ValueError:
        return []
    if cuis_idx is None:
        return []
    raw = data["p"].get(f"{cuis_idx},{ing_idx}", [])
    return [(data["i"][b], round(n / 100, 2)) for b, n in raw]


def bar(value: float, width: int = 20) -> str:
    filled = round(value * width)
    return "█" * filled + "░" * (width - filled)


def print_section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def compare(path_a: str, path_b: str, probe_ingredients: list[str]) -> None:
    a = load(path_a)
    b = load(path_b)

    label_a = Path(path_a).stem
    label_b = Path(path_b).stem

    # ── Overview ───────────────────────────────────────────────────────────
    print_section("OVERVIEW")
    metrics = [
        ("Ingredients",     len(a["i"]),              len(b["i"])),
        ("Cuisines",        len(a["c"]),               len(b["c"])),
        ("Pairing groups",  len(a["p"]),               len(b["p"])),
    ]
    print(f"  {'Metric':<20}  {label_a:>12}  {label_b:>12}  {'Δ':>8}")
    print(f"  {'─'*20}  {'─'*12}  {'─'*12}  {'─'*8}")
    for name, va, vb in metrics:
        delta = vb - va
        sign  = "+" if delta >= 0 else ""
        print(f"  {name:<20}  {va:>12,}  {vb:>12,}  {sign}{delta:>7,}")

    # ── New ingredients in full dataset ───────────────────────────────────
    new_ings = sorted(set(b["i"]) - set(a["i"]))
    print_section(f"INGREDIENTS IN {label_b} BUT NOT {label_a}  ({len(new_ings):,})")
    if new_ings:
        cols = 4
        for i in range(0, min(40, len(new_ings)), cols):
            print("  " + "  ".join(f"{x:<22}" for x in new_ings[i:i+cols]))
        if len(new_ings) > 40:
            print(f"  … and {len(new_ings) - 40} more")
    else:
        print("  None — ingredient set is identical.")

    # ── Missing ingredients ─────────────────────────────────────────────────
    dropped = sorted(set(a["i"]) - set(b["i"]))
    if dropped:
        print_section(f"INGREDIENTS IN {label_a} BUT NOT {label_b}  ({len(dropped):,})")
        print("  " + ", ".join(dropped[:40]))

    # ── Cuisine coverage ──────────────────────────────────────────────
    print_section("CUISINE COVERAGE")
    all_cuisines = sorted(set(a["c"]) | set(b["c"]))
    print(f"  {'Cuisine':<20}  {label_a:>8}  {label_b:>8}")
    print(f"  {'─'*20}  {'─'*8}  {'─'*8}")
    for c in all_cuisines:
        in_a = "✓" if c in a["c"] else "—"
        in_b = "✓" if c in b["c"] else "—"
        print(f"  {c:<20}  {in_a:>8}  {in_b:>8}")

    # ── Pairing drift for probe ingredients ─────────────────────────────
    print_section("PAIRING DRIFT  (top-10 pairs, all cuisines)")

    for ing in probe_ingredients:
        pairs_a = dict(get_pairings(a, ing))
        pairs_b = dict(get_pairings(b, ing))

        if not pairs_a and not pairs_b:
            continue

        print(f"\n  ┌─ {ing.upper()} {'─'*(54 - len(ing))}")
        print(f"  │  {'Paired with':<22}  {label_a:>8}  {label_b:>8}  {'Δ':>7}  Change")
        print(f"  │  {'─'*22}  {'─'*8}  {'─'*8}  {'─'*7}  {'─'*8}")

        all_pairs = dict(sorted(
            {**pairs_a, **pairs_b}.items(),
            key=lambda kv: -(pairs_b.get(kv[0], 0) or pairs_a.get(kv[0], 0))
        ))

        shown = 0
        for paired, _ in all_pairs.items():
            if shown >= 10:
                break
            sa = pairs_a.get(paired)
            sb = pairs_b.get(paired)
            sa_str = f"{sa:.2f}" if sa is not None else "  — "
            sb_str = f"{sb:.2f}" if sb is not None else "  — "
            if sa is not None and sb is not None:
                delta = sb - sa
                sign  = "+" if delta >= 0 else ""
                flag  = "▲" if delta > 0.05 else ("▼" if delta < -0.05 else "≈")
                d_str = f"{sign}{delta:.2f}"
            elif sb is not None:
                flag, d_str = "NEW", "   new"
            else:
                flag, d_str = "DEL", "  gone"
            print(f"  │  {paired:<22}  {sa_str:>8}  {sb_str:>8}  {d_str:>7}  {flag}")
            shown += 1

    print(f"\n{'─' * 60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file_a", help="Smaller dataset JSON (e.g. pairings_500k.json)")
    parser.add_argument("file_b", help="Larger dataset JSON  (e.g. pairings_full.json)")
    parser.add_argument(
        "--ingredients", nargs="+", default=PROBE_INGREDIENTS,
        metavar="ING", help="Ingredients to compare pairings for",
    )
    args = parser.parse_args()
    compare(args.file_a, args.file_b, args.ingredients)
