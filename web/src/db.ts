import type { Ingredient, Cuisine, Pairing } from "./types";

interface RawData {
  v: number;
  meta?: { source: string; recipes: number };
  i: string[];                            // ingredients[idx] = name
  c: string[];                            // cuisines[idx] = name, c[0] = "all"
  p: Record<string, [number, number][]>;  // "cuisineIdx,ingredientIdx" → [[pairedIdx, npmi*100], …]
}

let raw: RawData | null = null;

export async function loadDatabase(onProgress: (msg: string) => void): Promise<void> {
  onProgress("Fetching pairing data…");
  const res = await fetch(import.meta.env.BASE_URL + "pairings.json");
  if (!res.ok) throw new Error(`Failed to fetch pairings.json: ${res.status}`);
  onProgress("Parsing data…");
  raw = await res.json() as RawData;
}

function requireRaw(): RawData {
  if (!raw) throw new Error("Data not loaded");
  return raw;
}

export function getDataMeta(): { source: string; recipes: number } {
  return requireRaw().meta ?? { source: "demo", recipes: 0 };
}

export function getAllIngredients(): Ingredient[] {
  const raw = requireRaw();
  // Count total pairing relationships per ingredient across all cuisines as popularity proxy
  const freq = new Array(raw.i.length).fill(0);
  for (const key of Object.keys(raw.p)) {
    const ingIdx = parseInt(key.split(",")[1]);
    freq[ingIdx] += raw.p[key].length;
  }
  return raw.i.map((name, id) => ({ id, name, freq: freq[id] }));
}

export function getAllCuisines(): Cuisine[] {
  return requireRaw().c.map((name, id) => ({ id, name, recipeCount: 0 }));
}

function getPairingsForIngredient(
  ingredientIdx: number,
  cuisineIdx: number
): Map<number, number> {
  const entries = requireRaw().p[`${cuisineIdx},${ingredientIdx}`] ?? [];
  return new Map(entries.map(([pairedIdx, npmiInt]) => [pairedIdx, npmiInt / 100]));
}

export function getRecommendations(
  selectedIds: number[],
  allIngredients: Ingredient[],
  cuisineId: number,
  topN = 30
): Pairing[] {
  if (selectedIds.length === 0) return [];

  const n = selectedIds.length;
  const minCoverage = Math.max(1, Math.round(n * 0.5));
  const selectedSet = new Set(selectedIds);
  const ingredientById = new Map(allIngredients.map((i) => [i.id, i]));

  const scores = new Map<number, { sum: number; coverage: number }>();

  for (const sid of selectedIds) {
    for (const [bid, npmi] of getPairingsForIngredient(sid, cuisineId)) {
      if (selectedSet.has(bid)) continue;
      const existing = scores.get(bid);
      if (existing) {
        existing.sum += npmi;
        existing.coverage += 1;
      } else {
        scores.set(bid, { sum: npmi, coverage: 1 });
      }
    }
  }

  const results: Pairing[] = [];
  for (const [bid, { sum, coverage }] of scores) {
    if (coverage < minCoverage) continue;
    const ingredient = ingredientById.get(bid);
    if (!ingredient) continue;
    results.push({ ingredient, npmi: sum / n, cooccurrence: 0, coverage });
  }

  results.sort((a, b) => b.npmi - a.npmi);
  return results.slice(0, topN);
}
