#!/usr/bin/env python3
"""
Ingredient phrase -> canonical ingredient mapping (issue #56).

Maps a raw recipe ingredient phrase (English or French) onto the app's canonical
ingredient space -- the names that survive curation in the DEPLOYED
pairings.json. Recipe matching joins on these names, so a phrase that cannot be
mapped confidently is *dropped*, never guessed: a lost phrase only makes one
recipe slightly less specific, whereas a wrong map (the documented
"english muffin"->"muffin" incident) surfaces recipes for the wrong selection.

Cascade (each phrase stops at its first hit; the stage is recorded):
    C1 exact       exact match against canonical / merges / curation / alias / FR-inverse
    C2 normalized  lowercase, accent-fold, singularise, collapse whitespace
    C3 head-noun   peel leading qualifiers, try progressively shorter tails
    C5 fuzzy       difflib close-match at a HIGH cutoff (typos/spacing only)

C6 (a model stage for the survivors) is intentionally left as an optional hook
in build_recipes.py -- the deterministic stages here run fully offline and are
what the acceptance gate (>=90% of occurrences mapped deterministically) checks.
This module has no third-party dependencies.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from difflib import get_close_matches

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
PAIRINGS = os.path.join(ROOT, "web", "public", "pairings.json")
CURATION = os.path.join(ROOT, "pipeline", "curation.json")
MERGES = os.path.join(ROOT, "pipeline", "merges.json")
FR_JSON = os.path.join(ROOT, "web", "src", "translations", "fr.json")

FUZZY_CUTOFF = 0.9   # C5: catch typos / spacing / word-order only, never semantics

# Cooking aliases where the everyday word differs from the canonical name.
# Kept small and unambiguous; each is a culinary identity, not a guess.
ALIASES = {
    "cilantro": "coriander",
    "coriander leaf": "coriander",
    "scallion": "green onion",
    "scallions": "green onion",
    "spring onion": "green onion",
    "spring onions": "green onion",
    "mozzarella": "mozzarella cheese",
    "parmesan": "parmesan cheese",
    "parmigiano": "parmesan cheese",
    "parmigiano reggiano": "parmesan cheese",
    "cheddar": "cheddar cheese",
    "feta": "feta cheese",
    "gruyere": "gruyere cheese",
    "goat cheese": "goat cheese",
    "eggplant": "eggplant",
    "aubergine": "eggplant",
    "courgette": "zucchini",
    "prawn": "shrimp",
    "prawns": "shrimp",
    "coriandre": "coriander",
    "oignon": "onion",
    "ail": "garlic",
    "beurre": "butter",
    "oeuf": "egg",
    "citron": "lemon",
    "citron vert": "lime",
    "creme fraiche": "sour cream",
    "champignon": "mushroom",
    "champignon de paris": "mushroom",
    "echalote": "shallot",
    "poireau": "leek",
    "estragon": "tarragon",
    "canard": "duck",
    "veau": "veal",
    "moule": "mussel",
    "vin blanc": "white wine",
    "vin rouge": "red wine",
}

# Leading qualifier words peeled in C3 (English + a few French).
QUALIFIERS = {
    "fresh", "dried", "ground", "chopped", "minced", "grated", "sliced",
    "whole", "large", "small", "medium", "ripe", "raw", "cooked", "boneless",
    "skinless", "extra", "virgin", "unsalted", "salted", "organic", "frozen",
    "canned", "crushed", "shredded", "finely", "roughly", "peeled", "smoked",
    "toasted", "roasted", "cold", "warm", "hot", "plain", "pure", "light",
    "dark", "sweet", "sour", "hard", "soft", "lean", "thin", "thick",
    "petit", "petite", "gros", "grosse", "frais", "fraiche", "sec", "seche",
    "hache", "hachee", "emince", "emincee", "rape", "rapee",
}


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                    if not unicodedata.combining(c))


def singularise(s):
    # Deliberately conservative English/French plural rules.
    for suf, repl in (("ies", "y"), ("ves", "f"), ("oes", "o"), ("aux", "al"),
                      ("es", ""), ("s", "")):
        if s.endswith(suf) and len(s) - len(suf) >= 2:
            return s[: -len(suf)] + repl
    return s


def fold(s):
    return singularise(strip_accents(s.lower()).strip())


def deployed_names(pairings_path=PAIRINGS, curation_path=CURATION):
    """Canonical names that survive curation, i.e. the DEPLOYED ingredient set."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        with open(pairings_path, encoding="utf-8") as f:
            data = json.load(f)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        subprocess.run(
            [sys.executable, os.path.join(ROOT, "pipeline", "apply_curation_json.py"),
             curation_path, tmp_path],
            check=True, capture_output=True,
        )
        with open(tmp_path, encoding="utf-8") as f:
            return list(json.load(f)["i"])
    finally:
        os.unlink(tmp_path)


class Mapper:
    """Deterministic phrase -> canonical-name mapper. Reuses the project's own
    normalisation assets (merges.json, curation.merged, the FR dictionary)."""

    def __init__(self):
        self.canonical = deployed_names()
        canon_set = set(self.canonical)

        # variant -> canonical, from every normalisation decision ever made,
        # keeping only those whose final target is still deployed.
        variants = {}

        with open(MERGES, encoding="utf-8") as f:
            for src, tgt in json.load(f).items():
                variants[src] = tgt

        with open(CURATION, encoding="utf-8") as f:
            merged = json.load(f).get("merged", {})
        for src in list(merged):
            tgt, seen = merged[src], {src}
            while tgt in merged and tgt not in seen:
                seen.add(tgt)
                tgt = merged[tgt]
            variants[src] = tgt

        variants.update(ALIASES)

        # FR -> EN, inverted from the EN->FR dictionary (prefer the canonical
        # with more pairs when a French name is shared -- approximated by the
        # first canonical seen, which the dict orders by frequency).
        try:
            with open(FR_JSON, encoding="utf-8") as f:
                for en, fr in json.load(f).items():
                    if isinstance(fr, str):
                        variants.setdefault(fr.lower(), en)
        except FileNotFoundError:
            pass

        # Resolve each variant to a deployed canonical (follow one hop through
        # canonical set / aliases).
        def resolve(name):
            if name in canon_set:
                return name
            hop = variants.get(name) or ALIASES.get(name)
            return hop if hop in canon_set else None

        # Build folded lookup tables over canonical names + resolvable variants.
        self.by_fold = {}
        for name in self.canonical:
            self.by_fold.setdefault(fold(name), name)
        self.variant_to_canon = {}
        for v in variants:
            r = resolve(v)
            if r:
                self.variant_to_canon[v.lower()] = r
                self.by_fold.setdefault(fold(v), r)

        self.canon_set = canon_set

    def map_phrase(self, phrase):
        """Return (canonical_name, stage) or (None, 'unmapped')."""
        p = re.sub(r"\s+", " ", phrase.strip().lower())
        if not p:
            return None, "unmapped"

        # C1 exact
        if p in self.canon_set:
            return p, "C1"
        if p in self.variant_to_canon:
            return self.variant_to_canon[p], "C1"

        # C2 normalized (accent-fold + singularise)
        f = fold(p)
        if f in self.by_fold:
            return self.by_fold[f], "C2"

        # C3 head-noun: peel leading qualifiers, then try shrinking tails
        words = [w for w in re.split(r"[\s,]+", p) if w]
        core = [w for w in words if w not in QUALIFIERS] or words
        for start in range(len(core)):
            for end in range(len(core), start, -1):
                cand = " ".join(core[start:end])
                if cand in self.canon_set:
                    return cand, "C3"
                if cand in self.variant_to_canon:
                    return self.variant_to_canon[cand], "C3"
                cf = fold(cand)
                if cf in self.by_fold:
                    return self.by_fold[cf], "C3"

        # C5 fuzzy: high cutoff, typos/spacing only
        m = get_close_matches(f, list(self.by_fold.keys()), n=1, cutoff=FUZZY_CUTOFF)
        if m:
            return self.by_fold[m[0]], "C5"

        return None, "unmapped"


if __name__ == "__main__":
    mapper = Mapper()
    print(f"{len(mapper.canonical)} deployed canonical names")
    for phrase in sys.argv[1:]:
        print(f"  {phrase!r:40} -> {mapper.map_phrase(phrase)}")
