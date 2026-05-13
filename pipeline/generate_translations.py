"""
Generate French translations for all FlavorGraph ingredient names.

Usage:
  pip install anthropic
  python pipeline/generate_translations.py \
    --output web/src/translations/fr.json

Fetches ingredient names from FlavorGraph, translates missing entries via
Claude Haiku in batches of 100, and merges results into the existing fr.json
(preserving UI strings and any existing hand-crafted translations).
"""

import argparse
import csv
import json
import os
import time
import urllib.request

import anthropic

NODES_URL = "https://raw.githubusercontent.com/lamypark/FlavorGraph/master/input/nodes_191120.csv"
BATCH_SIZE = 100
MODEL = "claude-haiku-4-5-20251001"


def fetch_ingredient_names() -> list[str]:
    print(f"Fetching {NODES_URL} …", flush=True)
    with urllib.request.urlopen(NODES_URL) as r:
        lines = r.read().decode("utf-8").splitlines()
    rows = list(csv.DictReader(lines))
    names = [
        row["name"].replace("_", " ").strip().lower()
        for row in rows
        if row["node_type"] == "ingredient"
    ]
    print(f"  {len(names)} ingredient names", flush=True)
    return names


def translate_batch(client: anthropic.Anthropic, names: list[str]) -> dict[str, str]:
    prompt = (
        "Translate these English food ingredient names to French culinary terms.\n"
        "Return ONLY a JSON object mapping each English name to its French translation — no markdown, no explanation.\n"
        "Rules:\n"
        "- Use standard French culinary vocabulary\n"
        "- Keep brand names, abbreviations and percentages unchanged (e.g. '7 up', '2%')\n"
        "- For compound names, translate each component appropriately\n"
        "- Prefer the most common French culinary term\n"
        "- If no good French equivalent exists, keep the English name\n\n"
        "Names to translate:\n"
        + json.dumps(names, ensure_ascii=False)
    )

    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    start = text.find("{")
    end = text.rfind("}") + 1
    return json.loads(text[start:end])


def main(output: str) -> None:
    names = fetch_ingredient_names()

    with open(output, encoding="utf-8") as f:
        existing: dict[str, str] = json.load(f)

    missing = [n for n in names if n not in existing and n.lower() not in existing]
    print(f"  {len(existing)} existing entries, {len(missing)} to translate", flush=True)

    client = anthropic.Anthropic()
    new_translations: dict[str, str] = {}
    total = (len(missing) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(missing), BATCH_SIZE):
        batch = missing[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        print(f"  Batch {batch_num}/{total} ({len(batch)} names) …", end=" ", flush=True)
        try:
            result = translate_batch(client, batch)
            new_translations.update(result)
            print(f"✓ ({len(result)} translated)", flush=True)
        except Exception as e:
            print(f"✗ {e}", flush=True)
        if batch_num < total:
            time.sleep(0.3)

    merged = {**existing, **new_translations}

    with open(output, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    # Keep the static copy in sync for curate.html
    public_copy = os.path.join(os.path.dirname(__file__), "..", "web", "public", "translations", "fr.json")
    os.makedirs(os.path.dirname(public_copy), exist_ok=True)
    with open(public_copy, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(
        f"\nDone — {len(new_translations)} new translations added, "
        f"{len(merged)} total entries written to {output}",
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="web/src/translations/fr.json")
    args = parser.parse_args()
    main(args.output)
