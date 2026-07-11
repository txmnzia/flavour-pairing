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
    raw_merged   = curation.get('merged', {})   # from_name → to_name

    # Resolve merge chains (A→B, B→C ⇒ A→C) and enforce precedence:
    #   - a source that is also in `deleted` is dropped, not redirected
    #   - a chain ending on a deleted/unknown target means the source is dropped
    merged_names = {}
    for src, tgt in raw_merged.items():
        if src in deleted:
            continue
        seen = {src}
        while tgt in raw_merged and tgt not in deleted and tgt not in seen:
            seen.add(tgt)
            tgt = raw_merged[tgt]
        if tgt in deleted or tgt in seen or tgt not in name_to_old:
            deleted.add(src)   # nothing left to merge into — treat as deleted
        else:
            merged_names[src] = tgt

    removed = deleted | set(merged_names.keys())

    # Detect pairings format from actual keys (don't rely on missing 'v' field):
    #   v2: keys are plain "idx" strings — no cuisine dimension
    #   v1: keys are "cuisineIdx,idx"
    sample = next(iter(data['p']), '')
    v2 = ',' not in sample

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

    # Apply pair-level blacklist: remove the edge between two names in both
    # directions. Names are resolved through merges, so a badPair written
    # against a merged-away name still lands on its final target.
    def final_idx(name):
        if name in merged_names:
            name = merged_names[name]
        old = name_to_old.get(name)
        return old_to_new.get(old) if old is not None else None

    n_bad = 0
    for pair in curation.get('badPairs', []):
        if not (isinstance(pair, (list, tuple)) and len(pair) == 2):
            continue
        a, b = final_idx(pair[0]), final_idx(pair[1])
        if a is None or b is None or a == b:
            continue
        for x, y in ((a, b), (b, a)):
            key = make_key(0, x)
            if key in new_p:
                pruned = [p for p in new_p[key] if p[0] != y]
                if len(pruned) != len(new_p[key]):
                    new_p[key] = pruned
                    n_bad += 1
                if not new_p[key]:
                    del new_p[key]

    data['i'] = new_i
    data['p'] = new_p
    data.setdefault('meta', {})['ingredients'] = len(new_i)

    with open(pairings_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

    n_del    = len(deleted & set(old_i))
    n_merged = sum(1 for k in merged_names if k in name_to_old)
    print(f"Curation applied: {n_del} deleted, {n_merged} merged, "
          f"{n_bad} pair edges removed → {len(new_i)} ingredients remain")


if __name__ == '__main__':
    curation = sys.argv[1] if len(sys.argv) > 1 else CURATION
    pairings = sys.argv[2] if len(sys.argv) > 2 else PAIRINGS
    apply(os.path.abspath(curation), os.path.abspath(pairings))
