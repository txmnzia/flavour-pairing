#!/usr/bin/env python3
"""
Structural consistency validator for the pairing database (stdlib only).

Validates the committed base, the curation file, the taxonomy, and the
deploy-time transform output. Any failure exits non-zero — CI runs this on
every push (.github/workflows/validate.yml), and it must pass before merging
any change to data files or pipeline scripts.

Usage:
    python pipeline/validate_pairings.py            # validate everything
    python pipeline/validate_pairings.py --deployed-out PATH
                                                    # also keep the deployed
                                                    # JSON for downstream tests
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter

ROOT      = os.path.join(os.path.dirname(__file__), '..')
PAIRINGS  = os.path.join(ROOT, 'web', 'public', 'pairings.json')
TAXONOMY  = os.path.join(ROOT, 'web', 'public', 'taxonomy.json')
CURATION  = os.path.join(ROOT, 'pipeline', 'curation.json')
APPLY     = os.path.join(ROOT, 'pipeline', 'apply_curation_json.py')

VALID_CATS = {
    'meat', 'seafood', 'dairy', 'egg', 'vegetable', 'fruit', 'herb', 'spice',
    'starch', 'legume-nut', 'fat', 'condiment', 'sweet', 'beverage', 'alcohol',
    'other',
}

failures = []


def check(ok, msg):
    status = 'ok  ' if ok else 'FAIL'
    print(f"  [{status}] {msg}")
    if not ok:
        failures.append(msg)


def validate_structure(data, label):
    names = data['i']
    n = len(names)
    print(f"{label}: {n} ingredients, {len(data['p'])} pairing lists")

    dup = [x for x, c in Counter(names).items() if c > 1]
    check(not dup, f"{label}: no duplicate names (found {dup[:5] if dup else 'none'})")

    bad_keys = [k for k in data['p'] if not k.isdigit() or int(k) >= n]
    check(not bad_keys, f"{label}: all p-keys are plain in-range indices")

    self_pairs = out_of_range = bad_scores = dup_partners = 0
    for k, pairs in data['p'].items():
        ki = int(k)
        seen = set()
        for a, s in pairs:
            if a == ki: self_pairs += 1
            if not (0 <= a < n): out_of_range += 1
            if not (isinstance(s, int) and s >= 1): bad_scores += 1
            if a in seen: dup_partners += 1
            seen.add(a)
    check(self_pairs == 0, f"{label}: no self-pairs ({self_pairs})")
    check(out_of_range == 0, f"{label}: no out-of-range partner indices ({out_of_range})")
    check(bad_scores == 0, f"{label}: all scores are integers >= 1 ({bad_scores} bad)")
    check(dup_partners == 0, f"{label}: no duplicate partners within a list ({dup_partners})")

    # full symmetry: a->b implies b->a with the same score
    asym = 0
    p = {int(k): dict(map(tuple, v)) for k, v in data['p'].items()}
    for a, partners in p.items():
        for b, s in partners.items():
            if p.get(b, {}).get(a) != s:
                asym += 1
    check(asym == 0, f"{label}: edge symmetry ({asym} asymmetric)")

    # top-N cap detection: a hard cap shows up as a large spike of lists at
    # exactly one length below the max (see the TOP_N=50 incident)
    lengths = Counter(len(v) for v in data['p'].values())
    if lengths:
        mode_len, mode_count = lengths.most_common(1)[0]
        suspicious = mode_len > 10 and mode_count > 0.25 * len(data['p'])
        check(not suspicious,
              f"{label}: no top-N cap signature (mode length {mode_len} × {mode_count})")

    check(data.get('meta', {}).get('ingredients') == n,
          f"{label}: meta.ingredients matches actual count")


def validate_curation(base_names):
    cur = json.load(open(CURATION, encoding='utf-8'))
    deleted = cur.get('deleted', [])
    merged = cur.get('merged', {})
    bad_pairs = cur.get('badPairs', [])
    print(f"curation.json: {len(deleted)} deleted, {len(merged)} merged, {len(bad_pairs)} badPairs")

    check(isinstance(bad_pairs, list) and
          all(isinstance(p, list) and len(p) == 2 and
              all(isinstance(x, str) for x in p) for p in bad_pairs),
          "curation: badPairs is a list of [nameA, nameB] string pairs")

    self_merges = [a for a, b in merged.items() if a == b]
    check(not self_merges, f"curation: no self-merges ({self_merges[:3]})")

    # cycles in the merge map would hang naive resolvers
    def resolves(a):
        seen = set()
        while a in merged:
            if a in seen:
                return False
            seen.add(a)
            a = merged[a]
        return True
    cycles = [a for a in merged if not resolves(a)]
    check(not cycles, f"curation: merge map is cycle-free ({cycles[:3]})")

    unknown_src = [x for x in list(deleted) + list(merged) if x not in base_names]
    check(len(unknown_src) <= 5,
          f"curation: <=5 entries reference names missing from base ({len(unknown_src)}: {unknown_src[:5]})")


def validate_taxonomy(base_names):
    tax = json.load(open(TAXONOMY, encoding='utf-8'))
    print(f"taxonomy.json: {len(tax)} entries")
    missing = [n for n in base_names if n not in tax]
    check(not missing, f"taxonomy: covers every base name ({len(missing)} missing: {missing[:5]})")
    bad_cat = [n for n, e in tax.items() if e.get('c') not in VALID_CATS]
    check(not bad_cat, f"taxonomy: all categories valid ({bad_cat[:5]})")
    # base chains resolve without cycles
    def chain_ok(n):
        seen = {n}
        while True:
            b = tax.get(n, {}).get('b')
            if not b: return True
            if b in seen: return False
            seen.add(b); n = b
    cyc = [n for n in tax if not chain_ok(n)]
    check(not cyc, f"taxonomy: base chains are cycle-free ({cyc[:5]})")


def validate_deployed(deployed):
    validate_structure(deployed, 'deployed')
    names = deployed['i']
    no_pairs = [n for i, n in enumerate(names) if str(i) not in deployed['p']]
    check(not no_pairs, f"deployed: every ingredient has >=1 pair ({no_pairs[:5]})")
    n = len(names)
    check(800 <= n <= 2500,
          f"deployed: ingredient count {n} within sanity band [800, 2500]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--deployed-out', help='where to write the deployed JSON for downstream tests')
    args = ap.parse_args()

    base = json.load(open(PAIRINGS, encoding='utf-8'))
    validate_structure(base, 'base')
    validate_curation(set(base['i']))
    validate_taxonomy(base['i'])

    # run the real deploy transform on a copy
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, 'pairings.json')
        shutil.copy(PAIRINGS, copy)
        r = subprocess.run([sys.executable, APPLY, CURATION, copy],
                           capture_output=True, text=True)
        check(r.returncode == 0, f"deploy transform runs clean ({r.stderr.strip()[:200]})")
        if r.returncode == 0:
            deployed = json.load(open(copy, encoding='utf-8'))
            validate_deployed(deployed)
            if args.deployed_out:
                shutil.copy(copy, args.deployed_out)
                print(f"deployed JSON written to {args.deployed_out}")

    if failures:
        print(f"\n{len(failures)} FAILURE(S):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("\nAll consistency checks passed.")


if __name__ == '__main__':
    main()
