import type { CategoryLane, Ingredient, Pairing } from "./types";

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
  rarityStats = null;   // rebuilt lazily from the new data

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

// Taxonomy category slug for an ingredient name (e.g. "spice", "dairy").
// Falls back to "other" for unmapped names. Taxonomy is loaded in
// loadDatabase() before any tile renders, so this resolves synchronously.
export function getIngredientCategory(name: string): string {
  return taxonomy[name]?.c ?? "other";
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
  meat: 0.35, seafood: 0.35, spice: 0.45, beverage: 0.4, alcohol: 0.4,
  fruit: 0.5, fat: 0.5, starch: 0.55, sweet: 0.7, condiment: 0.7,
  "legume-nut": 0.7, herb: 0.75, dairy: 0.8, vegetable: 1, egg: 1, other: 1,
};
// Cross-category groups: meat and seafood demote each other (surf & turf is
// the exception, not the suggestion); alcohol and soft drinks likewise.
// LOO/harmony scoring is untouched: penalties shape the suggestion list only,
// never the compatibility measurement.
const PROTEIN = new Set(["meat", "seafood"]);
const DRINKS = new Set(["alcohol", "beverage"]);
// Global damp, applied regardless of selection: the corpus is full of cocktail
// recipes, so alcohol dominates fruit/aromatic suggestions unless held back.
const GLOBAL_DAMP: Record<string, number> = { alcohol: 0.6 };
// Diversity decay (issue #43 option B): each additional suggestion from an
// already-shown category is progressively demoted, so three near-identical
// drinks (wine / rice wine / sake) can't monopolise the first grid page.
const DIVERSITY_DECAY = 0.8;

// Rarity debias (issue #45). NPMI structurally favours *distinctive*
// co-occurrence: niche aromatics that appear almost exclusively alongside one
// ingredient (galangal median score 37) crush ubiquitous partners (garlic
// median 12), which is why cocktail liqueurs used to wall out honey for lemon.
// Each candidate's score is modulated by how exceptional the pair is FOR THAT
// CANDIDATE — a robust z-score against the candidate's own score
// distribution, clamped so it reweights rather than replaces the raw NPMI.
// Disable via ?ranking=raw to compare against the unmodulated ranking.
const RARITY_FLOOR = 0.25;
const RARITY_CAP = 1.5;
const RARITY_ENABLED =
  typeof location === "undefined" ||
  new URLSearchParams(location.search).get("ranking") !== "raw";

// candidateIdx → [median, IQR] of its own edge scores (×100 ints), built once
let rarityStats: Map<number, [number, number]> | null = null;

function getRarityStats(): Map<number, [number, number]> {
  if (rarityStats) return rarityStats;
  rarityStats = new Map();
  for (const [key, pairs] of Object.entries(requireRaw().p)) {
    const s = pairs.map(([, sc]) => sc).sort((a, b) => a - b);
    const q = (f: number) => s[Math.floor((s.length - 1) * f)];
    rarityStats.set(parseInt(key), [q(0.5), q(0.75) - q(0.25)]);
  }
  return rarityStats;
}

function rarityFactor(candidateIdx: number, avgScore100: number): number {
  if (!RARITY_ENABLED) return 1;
  const stats = getRarityStats().get(candidateIdx);
  if (!stats) return 1;
  const [median, iqr] = stats;
  const z = (avgScore100 - median) / Math.max(iqr, 5);
  return Math.min(Math.max(z, RARITY_FLOOR), RARITY_CAP);
}

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
  const damp = GLOBAL_DAMP[cat] ?? 1;
  if (selectedCats.has(cat)) return (SELF_PENALTY[cat] ?? 1) * damp;
  if (PROTEIN.has(cat) && [...PROTEIN].some((p) => selectedCats.has(p))) return 0.35 * damp;
  if (DRINKS.has(cat) && [...DRINKS].some((p) => selectedCats.has(p))) return 0.4 * damp;
  return damp;
}

// Shared scoring stage: every candidate that meets coverage, with the full
// penalty × rarity formula applied, sorted by score descending. Both the
// blended ranking (getRecommendations) and the category swimlanes (#52)
// consume this — the formula must never fork between the two views.
function scoreCandidates(
  selectedIds: number[],
  allIngredients: Ingredient[]
): (Pairing & { cat: string })[] {
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

  const candidates: (Pairing & { cat: string })[] = [];
  for (const [bid, { sum, coverage }] of scores) {
    if (coverage < minCoverage) continue;
    const ingredient = ingredientById.get(bid);
    if (!ingredient) continue;
    if (selectedBases.has(resolveBase(ingredient.name))) continue;
    const penalty = categoryPenalty(ingredient.name, selectedCats);
    const rarity = rarityFactor(bid, (sum / n) * 100);
    candidates.push({
      ingredient,
      score: (sum / n) * rarity * penalty,
      coverage,
      cat: taxonomy[ingredient.name]?.c ?? "other",
    });
  }

  candidates.sort((a, b) => b.score - a.score);
  return candidates;
}

export function getRecommendations(
  selectedIds: number[],
  allIngredients: Ingredient[],
  topN = 30
): Pairing[] {
  const candidates = scoreCandidates(selectedIds, allIngredients);

  // Greedy diversity selection: at each step pick the candidate with the best
  // decayed score, where the decay grows with how many suggestions of the same
  // category were already picked.
  const results: Pairing[] = [];
  const seen = new Map<string, number>();
  while (candidates.length > 0 && results.length < topN) {
    let bestIdx = 0;
    let bestEff = -Infinity;
    for (let i = 0; i < candidates.length; i++) {
      const eff = candidates[i].score * DIVERSITY_DECAY ** (seen.get(candidates[i].cat) ?? 0);
      if (eff > bestEff) {
        bestEff = eff;
        bestIdx = i;
      }
    }
    const { ingredient, coverage, cat } = candidates.splice(bestIdx, 1)[0];
    seen.set(cat, (seen.get(cat) ?? 0) + 1);
    // rarity can push a modulated score past 1 — clamp for the 0–99 badge
    results.push({ ingredient, score: Math.min(bestEff, 1), coverage });
  }
  return results;
}

// Category swimlanes (issue #52): the same scored candidates, grouped by
// taxonomy category instead of blended. Within a lane ranking is pure score —
// the diversity decay exists to stop one category monopolising the blended
// grid, which grouping already guarantees structurally. Lanes are ordered by
// their strongest candidate, so penalised categories (e.g. more meat when
// meat is selected) sink to the bottom rather than disappearing.
export function getRecommendationsByCategory(
  selectedIds: number[],
  allIngredients: Ingredient[],
  topPerCategory = 12
): CategoryLane[] {
  const lanes = new Map<string, Pairing[]>();
  // candidates arrive sorted by score, so each lane fills in ranked order
  for (const { ingredient, score, coverage, cat } of scoreCandidates(selectedIds, allIngredients)) {
    let lane = lanes.get(cat);
    if (!lane) {
      lane = [];
      lanes.set(cat, lane);
    }
    if (lane.length >= topPerCategory) continue;
    // rarity can push a modulated score past 1 — clamp for the 0–99 badge
    lane.push({ ingredient, score: Math.min(score, 1), coverage });
  }
  return [...lanes.entries()]
    .map(([category, pairings]) => ({ category, pairings }))
    .sort((a, b) => b.pairings[0].score - a.pairings[0].score);
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
