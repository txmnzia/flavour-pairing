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

CURATION  = os.path.join(os.path.dirname(__file__), 'curation.json')
PAIRINGS  = os.path.join(os.path.dirname(__file__), '..', 'web', 'public', 'pairings.json')


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

    # Names to remove from the ingredient list
    removed = deleted | set(merged_names.keys())

    # Build mapping: old index → new index
    # Deleted → None (drop)
    # Merged source → same new index as its target
    # Kept → sequential new index
    raw_map = {}   # old_idx → new_idx  (ints only after resolution)

    # First pass: assign new indices for kept ingredients
    new_i = []
    for old_idx, name in enumerate(old_i):
        if name not in removed:
            raw_map[old_idx] = len(new_i)
            new_i.append(name)

    # Second pass: resolve merge sources to their target's new index
    for old_idx, name in enumerate(old_i):
        if name in merged_names:
            target = merged_names[name]
            target_old = name_to_old.get(target)
            if target_old is not None and target_old in raw_map:
                raw_map[old_idx] = raw_map[target_old]
            # else target was also deleted/merged — drop source too

    old_to_new = raw_map  # missing key = drop this ingredient

    # Rebuild pairings
    new_p = {}
    for key, pairs in data['p'].items():
        ci_str, ii_str = key.split(',')
        ci, ii = int(ci_str), int(ii_str)

        new_ii = old_to_new.get(ii)
        if new_ii is None:
            continue  # ingredient dropped

        new_key = f"{ci},{new_ii}"

        # Remap paired indices, deduplicate, remove self-pairings
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
            # Merge with existing entry (happens when a source merges into a target)
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
