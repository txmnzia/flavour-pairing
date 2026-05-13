#!/usr/bin/env python3
"""
Apply curation decisions from pipeline/curation.json to pairings.db.

Run after downloading the latest curation.json from the repo
(git pull, then python pipeline/apply_curation.py).
"""
import argparse
import json
import os
import sqlite3

DEFAULT_CURATION = os.path.join(os.path.dirname(__file__), 'curation.json')
DEFAULT_DB       = os.path.join(os.path.dirname(__file__), '..', 'web', 'public', 'pairings.db')


def open_db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            "ALTER TABLE ingredients ADD COLUMN validated INTEGER NOT NULL DEFAULT 0"
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass
    return conn


def apply(curation_path, db_path, dry_run=False):
    with open(curation_path) as f:
        dec = json.load(f)

    validated = dec.get('validated', [])
    deleted   = dec.get('deleted',   [])
    merged    = dec.get('merged',    {})

    conn = open_db(db_path)

    def name_to_id(name):
        row = conn.execute("SELECT id FROM ingredients WHERE name=?", (name,)).fetchone()
        return row['id'] if row else None

    kept_v = kept_d = kept_m = 0

    # ── Validate ──────────────────────────────────────────────────────────────
    for name in validated:
        if not dry_run:
            conn.execute("UPDATE ingredients SET validated=1 WHERE name=?", (name,))
        kept_v += 1

    # ── Delete ────────────────────────────────────────────────────────────────
    for name in deleted:
        iid = name_to_id(name)
        if iid is None:
            print(f"  skip delete '{name}': not in DB")
            continue
        if not dry_run:
            conn.execute(
                "DELETE FROM pairings WHERE ingredient_a=? OR ingredient_b=?", (iid, iid)
            )
            conn.execute("DELETE FROM ingredients WHERE id=?", (iid,))
        kept_d += 1

    # ── Merge ─────────────────────────────────────────────────────────────────
    for from_name, into_name in merged.items():
        from_id = name_to_id(from_name)
        into_id = name_to_id(into_name)
        if from_id is None:
            print(f"  skip merge '{from_name}' → '{into_name}': source not in DB")
            continue
        if into_id is None:
            print(f"  skip merge '{from_name}' → '{into_name}': target not in DB")
            continue
        if not dry_run:
            conn.execute(
                """INSERT OR IGNORE INTO pairings
                     (ingredient_a, ingredient_b, cuisine_id, npmi, cooccurrence)
                   SELECT ?, ingredient_b, cuisine_id, npmi, cooccurrence
                   FROM pairings WHERE ingredient_a=? AND ingredient_b!=?""",
                (into_id, from_id, into_id),
            )
            conn.execute(
                """INSERT OR IGNORE INTO pairings
                     (ingredient_a, ingredient_b, cuisine_id, npmi, cooccurrence)
                   SELECT ingredient_a, ?, cuisine_id, npmi, cooccurrence
                   FROM pairings WHERE ingredient_b=? AND ingredient_a!=?""",
                (into_id, from_id, into_id),
            )
            conn.execute(
                "DELETE FROM pairings WHERE ingredient_a=? OR ingredient_b=?",
                (from_id, from_id),
            )
            conn.execute("DELETE FROM ingredients WHERE id=?", (from_id,))
        kept_m += 1

    if not dry_run:
        conn.commit()
    conn.close()

    tag = "[DRY RUN] " if dry_run else ""
    print(f"{tag}Applied: {kept_v} validated · {kept_d} deleted · {kept_m} merged")


def main():
    parser = argparse.ArgumentParser(description="Apply curation decisions to pairings.db")
    parser.add_argument("--curation", default=DEFAULT_CURATION, help="Path to curation.json")
    parser.add_argument("--db",       default=DEFAULT_DB,       help="Path to pairings.db")
    parser.add_argument("--dry-run",  action="store_true",      help="Preview without changing the DB")
    args = parser.parse_args()

    curation = os.path.abspath(args.curation)
    db_path  = os.path.abspath(args.db)

    if not os.path.exists(curation):
        print(f"Error: {curation} not found")
        print("Export it from the curation UI or run: git pull")
        raise SystemExit(1)

    if not os.path.exists(db_path):
        print(f"Error: {db_path} not found")
        print("Generate it first: python pipeline/generate_demo.py")
        raise SystemExit(1)

    apply(curation, db_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
