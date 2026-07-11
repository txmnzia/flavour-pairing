import type { Ingredient, Pairing } from "./types";

interface RawPairings {
  v: number;
  meta?: { source: string; ingredients?: number; recipes?: number };
  i: string[];                            // ingredients[idx] = name
  p: Record<string, [number, number][]>;  // "ingredientIdx" → [[pairedIdx, score*100], …]
}

interface RawRecipes {
  v: number;
  r: [string, string[]][];               // [title, [ingredientName, …]][]
}

// Taxonomy (issue #41): name → { c: category, b?: base/culinary parent }
type TaxEntry = { c: string; b?: string };
let taxonomy: Record<string, TaxEntry> = {};

let raw: RawPairings | null = null;

// Recipe inverted index: ingredientId → list of recipe indices
let recipeIndex: Map<number, number[]> | null = null;
let recipeTitles: string[] | null = null;

export async function loadDatabase(onProgress: (msg: string) => void): Promise<void> {
  onProgress("Fetching pairing data…");

  const base = import.meta.env.BASE_URL;
  const [pairingsRes, recipesRes, taxonomyRes] = await Promise.allSettled([
    fetch(base + "pairings.json"),
    fetch(base + "recipes.json"),
    fetch(base + "taxonomy.json"),
  ]);

  if (pairingsRes.status === "rejected" || !pairingsRes.value.ok) {
    const detail = pairingsRes.status === "rejected"
      ? pairingsRes.reason
      : pairingsRes.value.status;
    throw new Error(`Failed to fetch pairings.json: ${detail}`);
  }

  onProgress("Parsing data…");
  raw = await pairingsRes.value.json() as RawPairings;

  if (recipesRes.status === "fulfilled" && recipesRes.value.ok) {
    const rawRecipes = await recipesRes.value.json() as RawRecipes;
    buildRecipeIndex(rawRecipes);
  }

  // Optional: without it the engine degrades to raw NPMI ranking
  if (taxonomyRes.status === "fulfilled" && taxonomyRes.value.ok) {
    taxonomy = await taxonomyRes.value.json() as Record<string, TaxEntry>;
  }
}

function buildRecipeIndex(rawRecipes: RawRecipes): void {
  if (!raw || !rawRecipes.r?.length) return;

  const nameToId = new Map(raw.i.map((name, id) => [name, id]));
  recipeTitles = rawRecipes.r.map(([title]) => title);
  recipeIndex = new Map();

  rawRecipes.r.forEach(([_title, ingNames], rIdx) => {
    for (const name of ingNames) {
      const id = nameToId.get(name);
      if (id === undefined) continue;
      const existing = recipeIndex!.get(id);
      if (existing) {
        existing.push(rIdx);
      } else {
        recipeIndex!.set(id, [rIdx]);
      }
    }
  });
}

function requireRaw(): RawPairings {
  if (!raw) throw new Error("Data not loaded");
  return raw;
}

export function getDataMeta(): { source: string; recipes: number } {
  const meta = requireRaw().meta;
  return { source: meta?.source ?? "demo", recipes: meta?.recipes ?? 0 };
}

export function getAllIngredients(): Ingredient[] {
  const raw = requireRaw();
  const freq = new Array(raw.i.length).fill(0);
  for (const key of Object.keys(raw.p)) {
    const ingIdx = parseInt(key);
    freq[ingIdx] += raw.p[key].reduce((sum, [, s]) => sum + s, 0);
  }
  return raw.i.map((name, id) => ({ id, name, freq: freq[id] }));
}

function getPairingsForIngredient(ingredientIdx: number): Map<number, number> {
  const entries = requireRaw().p[String(ingredientIdx)] ?? [];
  return new Map(entries.map(([pairedIdx, scoreInt]) => [pairedIdx, scoreInt / 100]));
}

// Same-category demotion (issue #43). Co-occurrence rewards clusters — spice
// blends, citrus in cocktails, mixed-meat dishes — but a suggestion engine
// should surface complements, so candidates sharing a category with a selected
// ingredient are demoted. The factor encodes how unwelcome a same-category
// suggestion is: another protein next to a protein is nearly useless (0.35),
// while vegetables combine freely (1 = no demotion).
const SELF_PENALTY: Record<string, number> = {
  meat: 0.35, seafood: 0.35, spice: 0.45, beverage: 0.4, fruit: 0.5,
  fat: 0.5, starch: 0.55, sweet: 0.7, condiment: 0.7, "legume-nut": 0.7,
  herb: 0.75, dairy: 0.8, vegetable: 1, egg: 1, other: 1,
};
// meat and seafood demote each other too — surf & turf is the exception, not
// the suggestion. LOO/harmony scoring is untouched: penalties shape the
// suggestion list only, never the compatibility measurement.
const PROTEIN = new Set(["meat", "seafood"]);

// Same-base variant suppression (issue #44): never suggest a preparation or
// derivative of something already on the board (potato → hash brown,
// chicken → schmaltz, orange zest ↔ orange). `b` links only cover
// derivative relationships — see pipeline/generate_taxonomy.py.
function resolveBase(name: string): string {
  let cur = name;
  const seen = new Set([cur]);
  for (;;) {
    const next = taxonomy[cur]?.b;
    if (!next || seen.has(next)) return cur;
    seen.add(next);
    cur = next;
  }
}

function categoryPenalty(candidate: string, selectedCats: Set<string>): number {
  const cat = taxonomy[candidate]?.c;
  if (!cat) return 1;
  if (selectedCats.has(cat)) return SELF_PENALTY[cat] ?? 1;
  if (PROTEIN.has(cat) && [...PROTEIN].some((p) => selectedCats.has(p))) return 0.35;
  return 1;
}

export function getRecommendations(
  selectedIds: number[],
  allIngredients: Ingredient[],
  topN = 30
): Pairing[] {
  if (selectedIds.length === 0) return [];

  const n = selectedIds.length;
  const minCoverage = Math.max(1, Math.round(n * 0.5));
  const selectedSet = new Set(selectedIds);
  const ingredientById = new Map(allIngredients.map((i) => [i.id, i]));
  const selectedCats = new Set<string>();
  const selectedBases = new Set<string>();
  for (const sid of selectedIds) {
    const name = ingredientById.get(sid)?.name;
    if (!name) continue;
    const cat = taxonomy[name]?.c;
    if (cat) selectedCats.add(cat);
    selectedBases.add(resolveBase(name));
  }

  const scores = new Map<number, { sum: number; coverage: number }>();

  for (const sid of selectedIds) {
    for (const [bid, score] of getPairingsForIngredient(sid)) {
      if (selectedSet.has(bid)) continue;
      const existing = scores.get(bid);
      if (existing) {
        existing.sum += score;
        existing.coverage += 1;
      } else {
        scores.set(bid, { sum: score, coverage: 1 });
      }
    }
  }

  const results: Pairing[] = [];
  for (const [bid, { sum, coverage }] of scores) {
    if (coverage < minCoverage) continue;
    const ingredient = ingredientById.get(bid);
    if (!ingredient) continue;
    if (selectedBases.has(resolveBase(ingredient.name))) continue;
    const penalty = categoryPenalty(ingredient.name, selectedCats);
    results.push({ ingredient, score: (sum / n) * penalty, coverage });
  }

  results.sort((a, b) => b.score - a.score);
  return results.slice(0, topN);
}

export function computeLooScores(selectedIds: number[]): Map<number, number> {
  if (selectedIds.length < 2) return new Map();
  const result = new Map<number, number>();
  for (const x of selectedIds) {
    const xPairs = getPairingsForIngredient(x);
    const others = selectedIds.filter((id) => id !== x);
    const sum = others.reduce((acc, y) => {
      const fromX = xPairs.get(y) ?? 0;
      const fromY = getPairingsForIngredient(y).get(x) ?? 0;
      return acc + Math.max(fromX, fromY);
    }, 0);
    result.set(x, sum / others.length);
  }
  return result;
}

export function getRecipesForIngredients(ids: number[], limit = 8): string[] {
  if (!recipeTitles || !recipeIndex || ids.length === 0) return [];

  const firstList = recipeIndex.get(ids[0]);
  if (!firstList) return [];
  let candidates = new Set(firstList);

  for (let i = 1; i < ids.length; i++) {
    if (candidates.size === 0) return [];
    const nextSet = new Set(recipeIndex.get(ids[i]) ?? []);
    candidates = new Set([...candidates].filter((x) => nextSet.has(x)));
  }

  return [...candidates].slice(0, limit).map((idx) => recipeTitles![idx]);
}
