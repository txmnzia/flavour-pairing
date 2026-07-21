#!/usr/bin/env python3
"""
Build web/public/recipes.json (v2) from one or more normalized recipe corpora
(issue #56).

Input: normalized JSONL, one recipe per line, as emitted by the adapters
(pipeline/recipes/adapters/*.py) or the committed seed corpus:

    {"id": "...", "title": "Blanquette de veau", "lang": "fr",
     "ingredients": ["veal", "mushroom", "cream", ...],
     "url": "https://...", "source": "seed"}

Pipeline: map every ingredient phrase -> canonical (pipeline/recipes/mapping.py),
filter to recipes that are mostly canonical, dedupe, budget to a target size
with an ingredient-coverage-first pass, then emit the integer-encoded v2 file
plus a provenance manifest and a small deterministic test fixture.

    python3 pipeline/recipes/build_recipes.py                 # seed -> recipes.json
    python3 pipeline/recipes/build_recipes.py --input a.jsonl --input b.jsonl \
            --target 50000 --source recipenlg+marmiton
"""
import argparse
import json
import os
import re
from collections import Counter

from mapping import Mapper

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SEED = os.path.join(HERE, "seed", "seed_recipes.jsonl")
OUT = os.path.join(ROOT, "web", "public", "recipes.json")
FIXTURE = os.path.join(ROOT, "web", "test", "fixtures", "recipes.sample.json")

MIN_INGREDIENTS = 3
MAX_INGREDIENTS = 20
MIN_MAP_RATIO = 0.6      # a recipe must be mostly canonical to be honest about "gap"
COVERAGE_QUOTA = 6       # coverage pass: aim for >= this many recipes per ingredient
DETERMINISTIC_STAGES = {"C1", "C2", "C3", "C4"}


def norm_title(t):
    return re.sub(r"\s+", " ", t.strip().lower())


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", action="append", help="normalized JSONL (repeatable)")
    ap.add_argument("--target", type=int, default=0, help="max recipes (0 = keep all)")
    ap.add_argument("--source", default="seed", help="meta.source label")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    inputs = args.input or [SEED]

    mapper = Mapper()
    stage_occurrences = Counter()
    kept, seen_keys = [], set()

    for path in inputs:
        for rec in load_jsonl(path):
            title = (rec.get("title") or "").strip()
            url = (rec.get("url") or "").strip()
            lang = rec.get("lang", "en")
            phrases = rec.get("ingredients") or rec.get("ner") or []
            if not title or lang not in ("en", "fr"):
                continue

            mapped, seen = [], set()
            for phrase in phrases:
                name, stage = mapper.map_phrase(str(phrase))
                stage_occurrences[stage] += 1
                if name and name not in seen:
                    seen.add(name)
                    mapped.append(name)

            total = len(phrases)
            ratio = len(mapped) / total if total else 0
            if not (MIN_INGREDIENTS <= len(mapped) <= MAX_INGREDIENTS):
                continue
            if ratio < MIN_MAP_RATIO:
                continue

            key = (lang, norm_title(title), frozenset(mapped))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            kept.append({"title": title, "ings": mapped, "url": url, "lang": lang})

    kept = budget(kept, args.target) if args.target else kept

    write_outputs(kept, args.source, args.out)
    report(kept, stage_occurrences)


def budget(recipes, target):
    """Coverage-first selection: first guarantee every ingredient appears in a
    few recipes (so no selection dead-ends), then fill by ingredient richness."""
    if len(recipes) <= target:
        return recipes
    chosen, chosen_set = [], set()
    have = Counter()
    # Pass 1: coverage quota.
    for rec in sorted(recipes, key=lambda r: -len(r["ings"])):
        if any(have[i] < COVERAGE_QUOTA for i in rec["ings"]):
            chosen.append(rec)
            chosen_set.add(id(rec))
            for i in rec["ings"]:
                have[i] += 1
            if len(chosen) >= target:
                return chosen
    # Pass 2: fill remaining budget by richness.
    for rec in sorted(recipes, key=lambda r: -len(r["ings"])):
        if id(rec) in chosen_set:
            continue
        chosen.append(rec)
        if len(chosen) >= target:
            break
    return chosen


def encode(recipes):
    """Integer-encode: shared canonical vocabulary + local index refs."""
    vocab, vocab_idx = [], {}
    for rec in recipes:
        for name in rec["ings"]:
            if name not in vocab_idx:
                vocab_idx[name] = len(vocab)
                vocab.append(name)
    rows = [[r["title"], [vocab_idx[n] for n in r["ings"]], r["url"], r["lang"]]
            for r in recipes]
    return vocab, rows


def write_outputs(recipes, source, out_path):
    vocab, rows = encode(recipes)
    n_en = sum(1 for r in recipes if r["lang"] == "en")
    n_fr = sum(1 for r in recipes if r["lang"] == "fr")
    doc = {
        "v": 2,
        "meta": {"source": source, "recipes": len(rows), "en": n_en, "fr": n_fr},
        "ing": vocab,
        "r": rows,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))

    # Small deterministic fixture for the client tests (first ~40 recipes,
    # re-encoded so the vocabulary is self-contained).
    sample = recipes[:40]
    svocab, srows = encode(sample)
    os.makedirs(os.path.dirname(FIXTURE), exist_ok=True)
    with open(FIXTURE, "w", encoding="utf-8") as f:
        json.dump({"v": 2, "meta": {"source": "fixture", "recipes": len(srows)},
                   "ing": svocab, "r": srows}, f, ensure_ascii=False, indent=0)

    # Provenance manifest.
    man_dir = os.path.join(ROOT, "pipeline", "corpora", source.replace("+", "_"))
    os.makedirs(man_dir, exist_ok=True)
    with open(os.path.join(man_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({
            "source": source,
            "recipes": len(rows), "en": n_en, "fr": n_fr,
            "vocabulary": len(vocab),
            "license": "derived fields only (title + canonical ingredient ids + "
                       "source url); see pipeline/DATA.md",
        }, f, ensure_ascii=False, indent=2)


def report(recipes, stages):
    total = sum(stages.values())
    det = sum(v for k, v in stages.items() if k in DETERMINISTIC_STAGES)
    mapped = total - stages.get("unmapped", 0)
    print(f"Recipes kept: {len(recipes)} "
          f"(en {sum(1 for r in recipes if r['lang']=='en')}, "
          f"fr {sum(1 for r in recipes if r['lang']=='fr')})")
    if total:
        print(f"Occurrence mapping: {mapped}/{total} mapped "
              f"({100*mapped/total:.1f}%); deterministic C1-C4 "
              f"{100*det/total:.1f}%  (gate: >=90%)")
        print(f"  stages: {dict(stages)}")


if __name__ == "__main__":
    main()
