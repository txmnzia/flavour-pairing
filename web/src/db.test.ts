/**
 * Ranking consistency probes — these encode behaviour the owner has signed
 * off on. Changes to the scoring formula, the penalties, the taxonomy, or the
 * ingredient data MUST keep these green (or consciously update them with the
 * reasoning in the commit message).
 *
 * They exercise the REAL engine (db.ts) against the REAL deployed data
 * (base + curation, built by test/global-setup.ts), so there is no replica
 * to drift.
 */
import { beforeAll, describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import {
  loadDatabase,
  getAllIngredients,
  getRecommendations,
  getRecommendationsByCategory,
  computeLooScores,
} from "./db";
import type { Ingredient, Pairing } from "./types";

const here = path.dirname(fileURLToPath(import.meta.url));
const DEPLOYED = path.join(here, "..", "test", ".deployed.json");
const TAXONOMY = path.join(here, "..", "public", "taxonomy.json");

let ingredients: Ingredient[];
let taxonomy: Record<string, { c: string; b?: string }>;

function byName(name: string): Ingredient {
  const ing = ingredients.find((i) => i.name === name);
  if (!ing) throw new Error(`ingredient not deployed: ${name}`);
  return ing;
}

function topN(names: string[], n = 9): Pairing[] {
  return getRecommendations(names.map((x) => byName(x).id), ingredients, 36).slice(0, n);
}

function cats(pairings: Pairing[]): string[] {
  return pairings.map((p) => taxonomy[p.ingredient.name]?.c ?? "other");
}

beforeAll(async () => {
  const files: Record<string, string> = {
    "pairings.json": DEPLOYED,
    "taxonomy.json": TAXONOMY,
  };
  // Serve local files through the fetch()es loadDatabase makes;
  // recipes.json intentionally 404s (not deployed).
  globalThis.fetch = (async (url: string) => {
    const name = Object.keys(files).find((f) => String(url).endsWith(f));
    if (!name) return { ok: false, status: 404 } as Response;
    const body = readFileSync(files[name], "utf-8");
    return { ok: true, status: 200, json: async () => JSON.parse(body) } as Response;
  }) as typeof fetch;

  await loadDatabase(() => {});
  ingredients = getAllIngredients();
  taxonomy = JSON.parse(readFileSync(TAXONOMY, "utf-8"));
});

describe("engine structure", () => {
  it("never recommends a selected ingredient", () => {
    const sel = ["chicken", "garlic", "lemon"];
    const recs = topN(sel, 36);
    for (const r of recs) expect(sel).not.toContain(r.ingredient.name);
  });

  it("returns scores in non-increasing order (greedy diversity invariant)", () => {
    for (const probe of ["soy sauce", "lemon", "pork"]) {
      const recs = topN([probe], 36);
      for (let i = 1; i < recs.length; i++) {
        expect(recs[i].score).toBeLessThanOrEqual(recs[i - 1].score + 1e-9);
      }
    }
  });

  it("empty selection yields no recommendations", () => {
    expect(getRecommendations([], ingredients, 36)).toEqual([]);
  });
});

describe("category re-ranking (#43)", () => {
  it("pork's top-9 contains no other protein", () => {
    for (const c of cats(topN(["pork"]))) {
      expect(["meat", "seafood"]).not.toContain(c);
    }
  });

  // Relaxed from "no spice" when the rarity debias (#45) landed: cinnamon+clove
  // is genuinely exceptional FOR clove, so one same-category suggestion is
  // acceptable — the complaint was the clove/cardamom/nutmeg/anise WALL.
  it("cinnamon's top-9 contains at most one other spice", () => {
    const spices = cats(topN(["cinnamon"])).filter((c) => c === "spice");
    expect(spices.length).toBeLessThanOrEqual(1);
  });

  it("shrimp's top-9 contains no meat (protein cross-penalty)", () => {
    expect(cats(topN(["shrimp"]))).not.toContain("meat");
  });
});

describe("alcohol damp + diversity decay", () => {
  it("soy sauce's top-9 contains no alcohol (the wine/rice wine/sake wall)", () => {
    expect(cats(topN(["soy sauce"]))).not.toContain("alcohol");
  });

  it("lemon's top-9 contains no alcohol (the cocktail wall)", () => {
    expect(cats(topN(["lemon"]))).not.toContain("alcohol");
  });

  it("no category occupies more than 4 of any top-9", () => {
    for (const probe of ["soy sauce", "lemon", "pork", "tomato", "chicken", "apple"]) {
      const counts = new Map<string, number>();
      for (const c of cats(topN([probe]))) counts.set(c, (counts.get(c) ?? 0) + 1);
      for (const [c, n] of counts) {
        expect(n, `${probe}: ${n}×${c} in top-9`).toBeLessThanOrEqual(4);
      }
    }
  });
});

describe("variant suppression (#44)", () => {
  it("potato never suggests hash brown", () => {
    const names = topN(["potato"], 36).map((p) => p.ingredient.name);
    expect(names).not.toContain("hash brown");
  });

  it("chicken never suggests its own derivatives", () => {
    const names = topN(["chicken"], 36).map((p) => p.ingredient.name);
    for (const v of ["schmaltz", "chicken fat", "chicken broth"]) {
      expect(names).not.toContain(v);
    }
  });

  // Curation audit (#49): zests fold into their fruit — lemon zest and orange
  // zest are merged, so neither exists as a deployed ingredient any more.
  it("zests are merged into their fruit, not deployed", () => {
    for (const zest of ["orange zest", "lemon zest"]) {
      expect(ingredients.find((i) => i.name === zest)).toBeUndefined();
    }
  });
});

describe("curation outcomes (#46)", () => {
  it("tuna suggests english muffin (tuna melt), not muffin", () => {
    const names = topN(["tuna"], 36).map((p) => p.ingredient.name);
    expect(names).toContain("english muffin");
    expect(names).not.toContain("muffin");
  });
});

describe("golden pairs — the discoveries the app exists for", () => {
  it("apple surfaces cinnamon in its top-9", () => {
    expect(topN(["apple"]).map((p) => p.ingredient.name)).toContain("cinnamon");
  });

  // tomato→pasta and tomato→chicken were dropped 2026-07-13: the owner's
  // graded judgments (#53) rate both 0 — "very basic pairings were graded 0;
  // pasta is not bringing any relevant flavour to tomatoes". The judgment set
  // is the authority on taste now; these probes only guard discovery wins.
  it.each([
    ["shrimp", "coriander"],
    ["soy sauce", "sesame oil"],
    // Rarity debias (#45) win — a cross-category cooking pair that the raw
    // NPMI ranking buried under niche-distinctive partners:
    ["lemon", "honey"],
  ])("%s surfaces %s in its top-9", (sel, expected) => {
    expect(topN([sel]).map((p) => p.ingredient.name)).toContain(expected);
  });

  it("scores stay within the badge range [0, 1]", () => {
    for (const probe of ["shrimp", "lemon", "pork"]) {
      for (const r of topN([probe], 36)) {
        expect(r.score).toBeGreaterThanOrEqual(0);
        expect(r.score).toBeLessThanOrEqual(1);
      }
    }
  });
});

describe("category swimlanes (#52)", () => {
  const laneProbes = ["chicken", "lemon", "soy sauce"];

  it("every lane is homogeneous and internally ranked by score", () => {
    for (const probe of laneProbes) {
      const lanes = getRecommendationsByCategory([byName(probe).id], ingredients, 12);
      expect(lanes.length).toBeGreaterThan(0);
      for (const lane of lanes) {
        expect(lane.pairings.length).toBeGreaterThan(0);
        expect(lane.pairings.length).toBeLessThanOrEqual(12);
        for (let i = 0; i < lane.pairings.length; i++) {
          const p = lane.pairings[i];
          expect(taxonomy[p.ingredient.name]?.c ?? "other").toBe(lane.category);
          expect(p.score).toBeGreaterThanOrEqual(0);
          expect(p.score).toBeLessThanOrEqual(1);
          if (i > 0) expect(p.score).toBeLessThanOrEqual(lane.pairings[i - 1].score + 1e-9);
        }
      }
    }
  });

  // Updated for #55: lanes were ordered by their single strongest candidate,
  // which let a category with one lucky pairing but a weak lane (e.g. pasta →
  // egg) outrank categories offering several solid options. Ordering now uses
  // the mean of each lane's top-3 scores, so a category ranks high by having a
  // cluster of strong candidates — "how likely the user is to add from here".
  const laneStrength = (ps: Pairing[]) => {
    const k = Math.min(3, ps.length);
    return ps.slice(0, k).reduce((s, p) => s + p.score, 0) / k;
  };
  it("lanes are ordered by the strength of their top candidates (#55)", () => {
    for (const probe of laneProbes) {
      const lanes = getRecommendationsByCategory([byName(probe).id], ingredients, 12);
      for (let i = 1; i < lanes.length; i++) {
        expect(laneStrength(lanes[i].pairings)).toBeLessThanOrEqual(
          laneStrength(lanes[i - 1].pairings) + 1e-9
        );
      }
    }
  });

  it("never contains a selected ingredient, and no category appears twice", () => {
    const sel = ["chicken", "garlic", "lemon"];
    const lanes = getRecommendationsByCategory(sel.map((x) => byName(x).id), ingredients, 12);
    const seenCats = new Set<string>();
    for (const lane of lanes) {
      expect(seenCats.has(lane.category)).toBe(false);
      seenCats.add(lane.category);
      for (const p of lane.pairings) expect(sel).not.toContain(p.ingredient.name);
    }
  });

  it("lane scores agree with the shared scoring stage: a lane's top candidate is the blended ranking's best of that category", () => {
    for (const probe of laneProbes) {
      const flat = getRecommendations([byName(probe).id], ingredients, 36);
      const lanes = getRecommendationsByCategory([byName(probe).id], ingredients, 12);
      const laneTop = new Map(lanes.map((l) => [l.category, l.pairings[0].ingredient.name]));
      const seen = new Set<string>();
      for (const r of flat) {
        const c = taxonomy[r.ingredient.name]?.c ?? "other";
        if (seen.has(c)) continue;
        seen.add(c);
        // the first blended suggestion of each category is that lane's #1
        expect(laneTop.get(c)).toBe(r.ingredient.name);
      }
    }
  });

  it("empty selection yields no lanes", () => {
    expect(getRecommendationsByCategory([], ingredients, 12)).toEqual([]);
  });
});

describe("LOO outlier detection", () => {
  it("chocolate is the clear outlier among garlic + onion + chocolate", () => {
    const ids = ["garlic", "onion", "chocolate"].map((n) => byName(n).id);
    const loo = computeLooScores(ids);
    const choc = loo.get(byName("chocolate").id)!;
    const garlic = loo.get(byName("garlic").id)!;
    const onion = loo.get(byName("onion").id)!;
    expect(choc).toBeLessThan(garlic);
    expect(choc).toBeLessThan(onion);
    expect(choc).toBeLessThan(0.5 * ((garlic + onion + choc) / 3));
  });

  it("LOO scores are within [0, 1] and defined for every selected id", () => {
    const ids = ["strawberry", "chocolate", "vanilla"].map((n) => byName(n).id);
    const loo = computeLooScores(ids);
    expect(loo.size).toBe(3);
    for (const v of loo.values()) {
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThanOrEqual(1);
    }
  });
});
