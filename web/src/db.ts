import type { CategoryLane, Ingredient, Pairing } from "./types";

interface RawPairings {
  v: number;
  meta?: { source: string; ingredients?: number; recipes?: number };
  i: string[];                            // ingredients[idx] = name
  p: Record<string, [number, number][]>;  // "ingredientIdx" → [[pairedIdx, score*100], …]
}

// recipes.json v2 (issue #56). Integer-encoded to keep the payload small:
// `ing` is the corpus ingredient vocabulary (canonical names, a subset of the
// deployed pairings `i`); each recipe references local indices into it.
interface RawRecipes {
  v: number;
  meta?: { source?: string; recipes?: number; en?: number; fr?: number };
  ing: string[];                                 // canonical ingredient vocabulary
  r: [string, number[], string, string][];       // [title, localIngIdx[], url, lang]
}

// A recipe after the vocabulary is resolved to DEPLOYED ingredient ids.
interface RecipeRec {
  title: string;
  ings: number[];   // deployed ingredient ids (deduped, unknown refs dropped)
  url: string;
  lang: string;     // "en" | "fr"
}

// A ranked recipe suggestion for a selection (issue #56).
export interface RecipeMatch {
  title: string;
  url: string;
  lang: string;
  used: string[];       // names of the SELECTED ingredients this recipe uses
  // SELECTED ingredients the recipe does NOT use, each with how well it would
  // pair with the dish (0–1) — "you could add basil, it fits" customisation.
  suggested: { name: string; fit: number }[];
  missing: number;      // how many other (unselected) ingredients the recipe needs
  approximate: boolean; // true when shown as a "closest match" (below the gate)
}

// Taxonomy (issue #41): name → { c: category, b?: base/culinary parent }
type TaxEntry = { c: string; b?: string };
let taxonomy: Record<string, TaxEntry> = {};

let raw: RawPairings | null = null;

// Recipes (issue #56), loaded lazily after the app is interactive.
let recipes: RecipeRec[] | null = null;
let recipeIndex: Map<number, number[]> | null = null;  // deployedIngId → recipe indices
let recipesReady = false;

export async function loadDatabase(onProgress: (msg: string) => void): Promise<void> {
  onProgress("Fetching pairing data…");

  const base = import.meta.env.BASE_URL;
  // recipes.json is fetched separately by loadRecipes() so its size never gates
  // first paint (issue #56).
  const [pairingsRes, taxonomyRes] = await Promise.allSettled([
    fetch(base + "pairings.json"),
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

  // Optional: without it the engine degrades to raw NPMI ranking
  if (taxonomyRes.status === "fulfilled" && taxonomyRes.value.ok) {
    taxonomy = await taxonomyRes.value.json() as Record<string, TaxEntry>;
  }
}

// Fetch and index the recipe corpus (issue #56). Called after the app is
// interactive so the ~MBs of recipe data never block the first render; the
// recipe suggestions simply appear once this resolves. Safe to call more than
// once (no-op after the first success) and tolerant of a missing file.
export async function loadRecipes(): Promise<void> {
  if (recipesReady || !raw) return;
  try {
    const res = await fetch(import.meta.env.BASE_URL + "recipes.json");
    if (!res.ok) return;
    const rawRecipes = await res.json() as RawRecipes;
    buildRecipeIndex(rawRecipes);
    recipesReady = true;
  } catch {
    // No corpus (or a fetch/parse failure) → feature stays hidden.
  }
}

export function areRecipesReady(): boolean {
  return recipesReady;
}

export function getRecipeCount(): number {
  return recipes?.length ?? 0;
}

function buildRecipeIndex(rawRecipes: RawRecipes): void {
  if (!raw || !rawRecipes.ing?.length || !rawRecipes.r?.length) return;

  // Resolve the corpus vocabulary to deployed ingredient ids once; a name that
  // did not survive curation resolves to undefined and its refs are dropped.
  const nameToId = new Map(raw.i.map((name, id) => [name, id]));
  const vocabToId = rawRecipes.ing.map((name) => nameToId.get(name));

  const built: RecipeRec[] = [];
  const index = new Map<number, number[]>();

  for (const [title, localIdxs, url, lang] of rawRecipes.r) {
    const ids: number[] = [];
    const seen = new Set<number>();
    for (const li of localIdxs) {
      const id = vocabToId[li];
      if (id === undefined || seen.has(id)) continue;
      seen.add(id);
      ids.push(id);
    }
    if (ids.length === 0) continue;   // nothing joins → useless for matching
    const rIdx = built.length;
    built.push({ title, ings: ids, url, lang });
    for (const id of ids) {
      const existing = index.get(id);
      if (existing) existing.push(rIdx);
      else index.set(id, [rIdx]);
    }
  }

  recipes = built;
  recipeIndex = index;
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

// Precompute the expensive rarity-stats cache. Otherwise it is built lazily
// on the first call to rarityFactor() — i.e. during the user's first ingredient
// selection — stalling that interaction by hundreds of ms on mobile. Call this
// once after load, off the interaction path.
export function warmCaches(): void {
  getRarityStats();
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
// grid, which grouping already guarantees structurally. Penalised categories
// (e.g. more meat when meat is selected) sink to the bottom rather than
// disappearing, because their candidates carry the SELF_PENALTY into the
// aggregate below.
//
// Lane ordering (issue #55): rank lanes by how likely the user is to add
// *something* from that category, not by a single lucky candidate. Ordering by
// the strongest candidate alone let a category with one exceptional pairing but
// an otherwise weak lane (e.g. pasta → egg: one strong edge, a near-zero
// second) float above categories offering several solid options. Instead we
// order by the mean of each lane's top few scores: a category earns a high
// position by having a cluster of strong candidates, which is what "likely to
// add from here" actually means. Falls back to the mean of whatever the lane
// holds when it has fewer than LANE_RANK_TOPK candidates.
const LANE_RANK_TOPK = 3;

function laneStrength(pairings: Pairing[]): number {
  const k = Math.min(LANE_RANK_TOPK, pairings.length);
  let sum = 0;
  for (let i = 0; i < k; i++) sum += pairings[i].score;
  return sum / k;
}

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
    .sort((a, b) => laneStrength(b.pairings) - laneStrength(a.pairings));
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

// Recipe ranking (issue #56). The old logic was a strict AND-intersection: a
// recipe had to contain EVERY selected ingredient, so two ingredients that
// never co-occur produced zero results and pairing strength was ignored.
// Instead we score every recipe that shares a meaningful subset of the
// selection and re-rank as ingredients are added, so the list refines without
// ever hard-dead-ending. Weights live here as tunable knobs, like the pairing
// ranking constants above.
const RW_COVER_YOU = 1.0;    // fraction of the SELECTION the recipe satisfies (primary)
const RW_MATCHED = 0.5;      // absolute overlap, diminishing (matched / (matched + K))
const RW_MATCHED_K = 3;
const RW_PAIRING = 0.6;      // do the matched ingredients pair well together (NPMI graph)
const RW_COVER_RECIPE = 0.3; // how close the recipe is to fully cookable (parsimony)
const RW_EXTRAS = 0.4;       // shopping-gap penalty, saturating (extras / (extras + E))
const RW_EXTRAS_E = 6;
const RW_SUGG_FIT = 0.5;     // reward recipes where your LEFTOVER picks pair well (mild)
const RECIPE_SCORE_CAP = 200; // full-score at most this many candidates (perf)
// A recipe must share at least this many of the selected ingredients to be
// worth suggesting — a single-ingredient overlap (e.g. every dessert that just
// contains "sugar") is noise. The requirement grows with the selection up to a
// cap, so it stays "at least 2, up to 4" rather than demanding the whole set.
const RECIPE_MIN_MATCH = 2;
const RECIPE_MAX_MATCH = 4;

// Average pairing strength among the selected ingredients a recipe uses — the
// "these ingredients pair well together in this dish" signal (issue #56).
// Symmetric max of the two directed NPMI scores; neutral when fewer than two
// matched so a single-ingredient hit is neither rewarded nor punished here.
function internalPairing(matchedIds: number[]): number {
  if (matchedIds.length < 2) return 0.3;
  let sum = 0;
  let pairs = 0;
  for (let a = 0; a < matchedIds.length; a++) {
    const aPairs = getPairingsForIngredient(matchedIds[a]);
    for (let b = a + 1; b < matchedIds.length; b++) {
      const fromA = aPairs.get(matchedIds[b]) ?? 0;
      const fromB = getPairingsForIngredient(matchedIds[b]).get(matchedIds[a]) ?? 0;
      sum += Math.max(fromA, fromB);
      pairs++;
    }
  }
  return pairs === 0 ? 0 : sum / pairs;
}

// How well one ingredient would pair with a whole dish (issue #56 — the "how
// well would basil fit this recipe" signal for customising a suggestion). Mean
// of its strongest few pairings with the recipe's ingredients, not the plain
// mean: fitting the dish's hero ingredients is what matters, and averaging over
// every ingredient (incl. neutral ones like onion) would dilute a real match.
const FIT_TOPK = 3;
function pairingFit(ingId: number, recipeIngs: number[]): number {
  const pairs = getPairingsForIngredient(ingId);
  const scores: number[] = [];
  for (const r of recipeIngs) {
    if (r === ingId) continue;
    const a = pairs.get(r) ?? 0;
    const b = getPairingsForIngredient(r).get(ingId) ?? 0;
    scores.push(Math.max(a, b));
  }
  if (scores.length === 0) return 0;
  scores.sort((x, y) => y - x);
  const top = scores.slice(0, FIT_TOPK);
  return top.reduce((s, x) => s + x, 0) / top.length;
}

export function getRecipeMatches(selectedIds: number[], lang: string, limit = 8): RecipeMatch[] {
  if (!recipes || !recipeIndex || selectedIds.length === 0) return [];

  const n = selectedIds.length;
  // Require ≥2 matched ingredients (never a single-ingredient hit), rising with
  // the selection toward a cap of 4, and never more than the selection itself.
  const gate = Math.min(
    n,
    Math.max(RECIPE_MIN_MATCH, Math.min(RECIPE_MAX_MATCH, Math.ceil(n * 0.6)))
  );
  const selectedSet = new Set(selectedIds);

  // Count how many of the selected ingredients each candidate recipe uses,
  // walking only the postings of the selected ingredients (no giant unions).
  const matchCount = new Map<number, number>();
  for (const sid of selectedIds) {
    for (const rIdx of recipeIndex.get(sid) ?? []) {
      matchCount.set(rIdx, (matchCount.get(rIdx) ?? 0) + 1);
    }
  }
  if (matchCount.size === 0) return [];

  // Clear the gate where possible; if nothing does, fall back to the closest
  // matches — but never below the 2-ingredient floor. Better to show nothing
  // than recipes that share a single ingredient.
  let pool = [...matchCount.entries()].filter(([, c]) => c >= gate);
  let approximate = false;
  if (pool.length === 0 && gate > RECIPE_MIN_MATCH) {
    pool = [...matchCount.entries()].filter(([, c]) => c >= RECIPE_MIN_MATCH);
    approximate = true;
  }
  if (pool.length === 0) return [];

  // Prefer the current UI language; borrow the other language only to top up.
  const primary = pool.filter(([r]) => recipes![r].lang === lang);
  const secondary = pool.filter(([r]) => recipes![r].lang !== lang);
  const ordered = (primary.length ? primary : pool);
  const overflow = primary.length ? secondary : [];

  // Cap the full-scoring set (internalPairing is the only O(m²) step) to the
  // best-covering candidates.
  const capped = [...ordered]
    .sort((a, b) => b[1] - a[1])
    .slice(0, RECIPE_SCORE_CAP);

  const scoreRecipe = (rIdx: number, matched: number) => {
    const rec = recipes![rIdx];
    const recSet = new Set(rec.ings);
    const total = rec.ings.length;
    const extras = Math.max(0, total - matched);            // recipe's own shopping gap
    const matchedIds = rec.ings.filter((id) => selectedSet.has(id));
    // Selected ingredients the recipe lacks — the customisation candidates,
    // each rated by how well it pairs with the whole dish.
    const suggested = selectedIds
      .filter((id) => !recSet.has(id))
      .map((id) => ({ name: raw!.i[id], fit: pairingFit(id, rec.ings) }))
      .sort((a, b) => b.fit - a.fit);
    const avgSuggFit = suggested.length
      ? suggested.reduce((s, x) => s + x.fit, 0) / suggested.length
      : 0;
    const coverageYou = matched / n;
    const coverageRecipe = total > 0 ? matched / total : 0;
    const score =
      RW_COVER_YOU * coverageYou +
      RW_MATCHED * (matched / (matched + RW_MATCHED_K)) +
      RW_PAIRING * internalPairing(matchedIds) +
      RW_COVER_RECIPE * coverageRecipe +
      RW_SUGG_FIT * avgSuggFit -
      RW_EXTRAS * (extras / (extras + RW_EXTRAS_E));
    return { rIdx, matched, extras, matchedIds, suggested, score };
  };

  const scored = capped.map(([rIdx, matched]) => scoreRecipe(rIdx, matched));
  scored.sort((a, b) => b.score - a.score || a.extras - b.extras);

  const toMatch = (s: ReturnType<typeof scoreRecipe>): RecipeMatch => {
    const rec = recipes![s.rIdx];
    return {
      title: rec.title,
      url: rec.url,
      lang: rec.lang,
      used: s.matchedIds.map((id) => raw!.i[id]),
      suggested: s.suggested,
      missing: s.extras,
      approximate,
    };
  };

  const results = scored.slice(0, limit).map(toMatch);

  // Top up with other-language closest matches only if we are short.
  if (results.length < limit && overflow.length) {
    const extra = overflow
      .sort((a, b) => b[1] - a[1])
      .slice(0, limit - results.length)
      .map(([rIdx, matched]) => toMatch(scoreRecipe(rIdx, matched)));
    results.push(...extra);
  }

  return results;
}
