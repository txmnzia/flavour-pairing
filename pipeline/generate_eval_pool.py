#!/usr/bin/env python3
"""
Generate the pooled candidate lists for the ranking evaluation (issue #50).

For each of 25 probe ingredients, pool the union of top-15 candidates under
several formula variants plus random mid-rank candidates, so the owner only
judges pairs that some plausible formula would actually surface (TREC-style
pooling). Candidates are shuffled deterministically so annotation order
carries no rank signal.

Output: web/public/eval/pool.json
    { "v": 1,
      "probes": [ {"name": "shrimp", "split": "dev", "candidates": ["...", ...]}, ... ] }

The dev/holdout split is committed here and must be respected by every tuning
script: HOLDOUT probes are never used to choose parameters.

Re-running is safe: pooling is deterministic for a given pairings/curation
state, and annotate.html keys judgments by (probe, candidate) name so existing
judgments always remain valid.
"""
import hashlib
import json
import os
import random
import statistics
import subprocess
import sys
import tempfile
import shutil

ROOT = os.path.join(os.path.dirname(__file__), '..')
OUT  = os.path.join(ROOT, 'web', 'public', 'eval', 'pool.json')

PROBES = [
    # pain points called out by the owner
    'shrimp', 'lemon', 'cinnamon', 'soy sauce', 'pork', 'tuna',
    # staples across categories
    'chicken', 'apple', 'potato', 'garlic', 'tomato', 'beef', 'salmon',
    'mushroom', 'onion', 'basil', 'ginger', 'chocolate', 'strawberry',
    'rice', 'egg', 'carrot', 'orange',
    # French-cuisine interest (also future #47 probes)
    'duck', 'leek',
]

TOP_PER_VARIANT = 15
RANDOM_EXTRAS   = 5      # sampled from raw ranks 20..120
SEED = 50                # issue number; do not change once annotation started

SELF = {'meat': 0.35, 'seafood': 0.35, 'spice': 0.45, 'beverage': 0.4,
        'alcohol': 0.4, 'fruit': 0.5, 'fat': 0.5, 'starch': 0.55,
        'sweet': 0.7, 'condiment': 0.7, 'legume-nut': 0.7, 'herb': 0.75,
        'dairy': 0.8, 'vegetable': 1, 'egg': 1, 'other': 1}
PROT = {'meat', 'seafood'}
DRINKS = {'alcohol', 'beverage'}


def build_deployed():
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, 'p.json')
        shutil.copy(os.path.join(ROOT, 'web', 'public', 'pairings.json'), copy)
        subprocess.run([sys.executable,
                        os.path.join(ROOT, 'pipeline', 'apply_curation_json.py'),
                        os.path.join(ROOT, 'pipeline', 'curation.json'), copy],
                       check=True, capture_output=True)
        return json.load(open(copy, encoding='utf-8'))


def main():
    d = build_deployed()
    tax = json.load(open(os.path.join(ROOT, 'web', 'public', 'taxonomy.json'), encoding='utf-8'))
    idx = {n: i for i, n in enumerate(d['i'])}

    med, iqr = {}, {}
    for k, v in d['p'].items():
        ss = sorted(s for _, s in v)
        med[int(k)] = statistics.median(ss)
        iqr[int(k)] = (statistics.quantiles(ss, n=4)[2] - statistics.quantiles(ss, n=4)[0]) if len(ss) >= 4 else 10

    def base(n):
        seen = {n}
        while tax.get(n, {}).get('b') and tax[n]['b'] not in seen:
            n = tax[n]['b']; seen.add(n)
        return n

    def rank(sel, use_penalties, rarity_floor, rarity_cap, decay):
        si = idx[sel]
        cats = {tax[sel]['c']} if sel in tax else set()
        sbase = {base(sel)}
        cands = []
        for bid, s100 in d['p'].get(str(si), []):
            name = d['i'][bid]
            if base(name) in sbase:
                continue
            s = s100 / 100
            if rarity_cap is not None:
                z = (s100 - med[bid]) / max(iqr[bid], 5)
                s *= min(max(z, rarity_floor), rarity_cap)
            if use_penalties:
                c = tax.get(name, {}).get('c')
                pen = 1.0
                if c in cats: pen = SELF.get(c, 1)
                elif c in PROT and cats & PROT: pen = 0.35
                elif c in DRINKS and cats & DRINKS: pen = 0.4
                pen *= 0.6 if c == 'alcohol' else 1
                s *= pen
            cands.append([s, name, tax.get(name, {}).get('c', 'other')])
        cands.sort(reverse=True)
        if decay is None:
            return [nm for _, nm, _ in cands]
        picked, seen = [], {}
        pool = list(cands)
        while pool and len(picked) < TOP_PER_VARIANT:
            bi = max(range(len(pool)), key=lambda i: pool[i][0] * (decay ** seen.get(pool[i][2], 0)))
            _, nm, c = pool.pop(bi)
            seen[c] = seen.get(c, 0) + 1
            picked.append(nm)
        return picked

    probes_out = []
    for p in PROBES:
        if p not in idx:
            raise SystemExit(f"probe not deployed: {p}")
        variants = [
            rank(p, False, None, None, None),      # V1 raw NPMI
            rank(p, True,  0.25, 1.5, 0.8),        # V2 current full chain
            rank(p, True,  None, None, 0.8),       # V3 penalties, no rarity
            rank(p, True,  0.10, 2.5, 0.8),        # V4 aggressive rarity
            rank(p, False, 0.25, 1.5, None),       # V5 rarity only, no penalties
        ]
        pool = []
        for v in variants:
            for nm in v[:TOP_PER_VARIANT]:
                if nm not in pool:
                    pool.append(nm)
        raw = variants[0]
        rng = random.Random(f"{SEED}:{p}")
        extras = [nm for nm in raw[20:120] if nm not in pool]
        pool += rng.sample(extras, min(RANDOM_EXTRAS, len(extras)))
        rng.shuffle(pool)   # presentation order carries no rank signal
        split = 'holdout' if int(hashlib.sha1(p.encode()).hexdigest(), 16) % 5 < 2 else 'dev'
        probes_out.append({'name': p, 'split': split, 'candidates': pool})

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump({'v': 1, 'probes': probes_out}, f, ensure_ascii=False, separators=(',', ':'))

    n = sum(len(p['candidates']) for p in probes_out)
    ndev = sum(1 for p in probes_out if p['split'] == 'dev')
    print(f"{len(probes_out)} probes ({ndev} dev / {len(probes_out)-ndev} holdout), "
          f"{n} judgments to collect (avg {n/len(probes_out):.0f}/probe) → {OUT}")


if __name__ == '__main__':
    main()
