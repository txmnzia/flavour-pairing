import initSqlJs, { type Database } from "sql.js";
import type { Ingredient, Cuisine, Pairing } from "./types";

let db: Database | null = null;

export async function loadDatabase(onProgress: (msg: string) => void): Promise<void> {
  onProgress("Loading SQL engine…");

  const SQL = await initSqlJs({
    locateFile: (file: string) => import.meta.env.BASE_URL + file,
  });

  onProgress("Fetching pairing data…");

  const response = await fetch(import.meta.env.BASE_URL + "pairings.db");
  if (!response.ok) throw new Error(`Failed to fetch pairings.db: ${response.status}`);

  const buffer = await response.arrayBuffer();
  onProgress("Initialising database…");

  db = new SQL.Database(new Uint8Array(buffer));
}

function requireDb(): Database {
  if (!db) throw new Error("Database not loaded");
  return db;
}

export function getAllIngredients(): Ingredient[] {
  const result = requireDb().exec(
    "SELECT id, name, freq FROM ingredients ORDER BY name ASC"
  );
  if (!result[0]) return [];
  return result[0].values.map(([id, name, freq]) => ({
    id: id as number,
    name: name as string,
    freq: freq as number,
  }));
}

export function getAllCuisines(): Cuisine[] {
  const result = requireDb().exec(
    "SELECT id, name, recipe_count FROM cuisines ORDER BY name ASC"
  );
  if (!result[0]) return [];
  return result[0].values.map(([id, name, recipeCount]) => ({
    id: id as number,
    name: name as string,
    recipeCount: recipeCount as number,
  }));
}

/**
 * Fetch top-N pairings for a single ingredient in a given cuisine.
 * Returns a map of ingredientId → {npmi, cooccurrence}.
 */
function getPairingsForIngredient(
  ingredientId: number,
  cuisineId: number,
  limit = 60
): Map<number, { npmi: number; cooccurrence: number }> {
  const result = requireDb().exec(
    `SELECT ingredient_b, npmi, cooccurrence
       FROM pairings
      WHERE ingredient_a = ? AND cuisine_id = ?
      ORDER BY npmi DESC
      LIMIT ?`,
    [ingredientId, cuisineId, limit]
  );
  const map = new Map<number, { npmi: number; cooccurrence: number }>();
  if (result[0]) {
    for (const [b, npmi, cooc] of result[0].values) {
      map.set(b as number, { npmi: npmi as number, cooccurrence: cooc as number });
    }
  }
  return map;
}

/**
 * Get combined recommendations for a set of selected ingredients.
 *
 * Scoring:
 *  - Fetch top-60 pairings for each selected ingredient.
 *  - For each candidate, sum NPMI scores across lists where it appears.
 *  - Divide by total number of selected ingredients (zeros drag down partial coverage).
 *  - Require candidate appears in at least max(1, round(n * 0.5)) lists.
 *  - Sort by combined score descending.
 */
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

  // Accumulate scores per candidate
  const scores = new Map<number, { sum: number; coverage: number; minCooc: number }>();

  for (const sid of selectedIds) {
    const pairings = getPairingsForIngredient(sid, cuisineId);
    for (const [bid, { npmi, cooccurrence }] of pairings) {
      if (selectedSet.has(bid)) continue; // skip already-selected
      const existing = scores.get(bid);
      if (existing) {
        existing.sum += npmi;
        existing.coverage += 1;
        existing.minCooc = Math.min(existing.minCooc, cooccurrence);
      } else {
        scores.set(bid, { sum: npmi, coverage: 1, minCooc: cooccurrence });
      }
    }
  }

  const results: Pairing[] = [];
  for (const [bid, { sum, coverage, minCooc }] of scores) {
    if (coverage < minCoverage) continue;
    const ingredient = ingredientById.get(bid);
    if (!ingredient) continue;
    results.push({
      ingredient,
      npmi: sum / n, // average across all selected (zeros for missing)
      cooccurrence: minCooc,
      coverage,
    });
  }

  results.sort((a, b) => b.npmi - a.npmi);
  return results.slice(0, topN);
}
