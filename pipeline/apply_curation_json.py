#!/usr/bin/env python3
"""
Apply curation decisions from pipeline/curation.json to web/public/pairings.json.

Called automatically by the deploy workflow after pairings.json is generated.
Can also be run manually:
    python pipeline/apply_curation_json.py
"""
import json
import os
import sys

CURATION = os.path.join(os.path.dirname(__file__), 'curation.json')
PAIRINGS = os.path.join(os.path.dirname(__file__), '..', 'web', 'public', 'pairings.json')


def apply(curation_path, pairings_path):
    if not os.path.exists(curation_path):
        print("No curation.json found — skipping.")
        return

    with open(curation_path, encoding='utf-8') as f:
        curation = json.load(f)
    with open(pairings_path, encoding='utf-8') as f:
        data = json.load(f)

    old_i = data['i']
    name_to_old = {n: i for i, n in enumerate(old_i)}

    deleted      = set(curation.get('deleted', []))
    merged_names = curation.get('merged', {})   # from_name → to_name
    removed      = deleted | set(merged_names.keys())

    # Detect pairings format:
    #   v2 (FlavorGraph): keys are plain "idx" strings — no cuisine dimension
    #   v1 (demo/RecipeNLG): keys are "cuisineIdx,idx"
    v2 = data.get('v', 1) >= 2

    def parse_key(k):
        if ',' in k:
            a, b = k.split(',', 1)
            return int(a), int(b)
        return 0, int(k)          # v2: treat as cuisine 0

    def make_key(ci, ii):
        return str(ii) if v2 else f"{ci},{ii}"

    # Build mapping: old index → new index
    # Kept ingredients get sequential new indices; merge sources map to their target.
    new_i = []
    kept_map = {}   # old_idx → new_idx  (for kept ingredients only)
    for old_idx, name in enumerate(old_i):
        if name not in removed:
            kept_map[old_idx] = len(new_i)
            new_i.append(name)

    old_to_new = dict(kept_map)
    for old_idx, name in enumerate(old_i):
        if name in merged_names:
            target = merged_names[name]
            target_old = name_to_old.get(target)
            if target_old is not None and target_old in kept_map:
                old_to_new[old_idx] = kept_map[target_old]
            # else target was also removed — source is simply dropped

    # Rebuild pairings
    new_p = {}
    for key, pairs in data['p'].items():
        ci, ii = parse_key(key)

        new_ii = old_to_new.get(ii)
        if new_ii is None:
            continue

        new_key = make_key(ci, new_ii)

        merged_pairs = {}
        for paired_idx, score in pairs:
            new_paired = old_to_new.get(paired_idx)
            if new_paired is None or new_paired == new_ii:
                continue
            if new_paired not in merged_pairs or score > merged_pairs[new_paired]:
                merged_pairs[new_paired] = score

        if not merged_pairs:
            continue

        if new_key not in new_p:
            new_p[new_key] = sorted(
                [[k, v] for k, v in merged_pairs.items()], key=lambda x: -x[1]
            )
        else:
            existing = {p[0]: p[1] for p in new_p[new_key]}
            for paired, score in merged_pairs.items():
                if paired not in existing or score > existing[paired]:
                    existing[paired] = score
            new_p[new_key] = sorted(
                [[k, v] for k, v in existing.items()], key=lambda x: -x[1]
            )

    data['i'] = new_i
    data['p'] = new_p
    data['meta']['ingredients'] = len(new_i)

    with open(pairings_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

    n_del    = len(deleted & set(old_i))
    n_merged = sum(1 for k in merged_names if k in name_to_old)
    print(f"Curation applied: {n_del} deleted, {n_merged} merged → {len(new_i)} ingredients remain")


if __name__ == '__main__':
    curation = sys.argv[1] if len(sys.argv) > 1 else CURATION
    pairings = sys.argv[2] if len(sys.argv) > 2 else PAIRINGS
    apply(os.path.abspath(curation), os.path.abspath(pairings))
