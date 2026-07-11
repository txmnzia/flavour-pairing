/**
 * Ranking evaluation report (issue #50) — scores the CURRENT formula against
 * the owner's graded judgments (pipeline/eval/judgments.json, written by
 * annotate.html).
 *
 * Grades: 2 = "I'd love the app to suggest this", 1 = fine/expected,
 * 0 = useless/wrong. Metrics per probe, averaged over dev and holdout splits
 * separately:
 *   - Precision@9:  fraction of top-9 with grade >= 1 (of judged ones)
 *   - Discovery@9:  fraction of top-9 with grade == 2
 *   - Recall@36:    fraction of the probe's grade-2 pairs found in top-36
 *   - nDCG@9:       graded ranking quality (the comparison scalar)
 *
 * This file REPORTS; it does not gate. Once baseline + targets are agreed
 * (issue #50 step 3), thresholds become assertions on the dev split.
 * Skips cleanly while annotation hasn't reached the minimum.
 */
import { beforeAll, describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { loadDatabase, getAllIngredients, getRecommendations } from "./db";
import type { Ingredient } from "./types";

const here = path.dirname(fileURLToPath(import.meta.url));
const DEPLOYED = path.join(here, "..", "test", ".deployed.json");
const TAXONOMY = path.join(here, "..", "public", "taxonomy.json");
const POOL = path.join(here, "..", "public", "eval", "pool.json");
const JUDGMENTS = path.join(here, "..", "..", "pipeline", "eval", "judgments.json");

const MIN_JUDGMENTS = 200;

type Judgments = Record<string, Record<string, number>>;

function loadJudgments(): Judgments | null {
  if (!existsSync(JUDGMENTS)) return null;
  const j = JSON.parse(readFileSync(JUDGMENTS, "utf-8")).judgments as Judgments;
  const n = Object.values(j).reduce((a, o) => a + Object.keys(o).length, 0);
  return n >= MIN_JUDGMENTS ? j : null;
}

const judgments = loadJudgments();

describe.skipIf(!judgments)("ranking evaluation vs owner judgments (#50)", () => {
  let ingredients: Ingredient[];
  let pool: { name: string; split: string }[];

  beforeAll(async () => {
    const files: Record<string, string> = {
      "pairings.json": DEPLOYED,
      "taxonomy.json": TAXONOMY,
    };
    globalThis.fetch = (async (url: string) => {
      const name = Object.keys(files).find((f) => String(url).endsWith(f));
      if (!name) return { ok: false, status: 404 } as Response;
      return { ok: true, status: 200, json: async () => JSON.parse(readFileSync(files[name], "utf-8")) } as Response;
    }) as typeof fetch;
    await loadDatabase(() => {});
    ingredients = getAllIngredients();
    pool = JSON.parse(readFileSync(POOL, "utf-8")).probes;
  });

  function metricsFor(probe: string) {
    const graded = judgments![probe] ?? {};
    const ing = ingredients.find((i) => i.name === probe);
    if (!ing || Object.keys(graded).length === 0) return null;
    const recs = getRecommendations([ing.id], ingredients, 36).map((r) => r.ingredient.name);
    const g = (n: string) => graded[n];               // undefined = unjudged
    const top9 = recs.slice(0, 9).filter((n) => g(n) !== undefined);
    if (top9.length === 0) return null;
    const p9 = top9.filter((n) => g(n)! >= 1).length / top9.length;
    const d9 = top9.filter((n) => g(n) === 2).length / top9.length;
    const loves = Object.keys(graded).filter((n) => graded[n] === 2);
    const r36 = loves.length ? loves.filter((n) => recs.includes(n)).length / loves.length : 1;
    // nDCG@9 over judged positions
    const dcg = top9.reduce((a, n, i) => a + (2 ** g(n)! - 1) / Math.log2(i + 2), 0);
    const ideal = Object.values(graded).sort((a, b) => b - a).slice(0, top9.length)
      .reduce((a, gr, i) => a + (2 ** gr - 1) / Math.log2(i + 2), 0);
    return { p9, d9, r36, ndcg: ideal ? dcg / ideal : 0, judgedInTop9: top9.length };
  }

  it("reports metrics per split (no thresholds until baseline is agreed)", () => {
    for (const split of ["dev", "holdout"]) {
      const rows = pool
        .filter((p) => p.split === split)
        .map((p) => ({ probe: p.name, m: metricsFor(p.name) }))
        .filter((r) => r.m);
      if (rows.length === 0) continue;
      const avg = (k: "p9" | "d9" | "r36" | "ndcg") =>
        rows.reduce((a, r) => a + r.m![k], 0) / rows.length;
      console.log(`\n=== ${split.toUpperCase()} (${rows.length} probes) ` +
        `P@9=${avg("p9").toFixed(3)} Discovery@9=${avg("d9").toFixed(3)} ` +
        `Recall@36=${avg("r36").toFixed(3)} nDCG@9=${avg("ndcg").toFixed(3)}`);
      for (const r of rows) {
        console.log(`  ${r.probe.padEnd(12)} P@9=${r.m!.p9.toFixed(2)} D@9=${r.m!.d9.toFixed(2)} ` +
          `R@36=${r.m!.r36.toFixed(2)} nDCG=${r.m!.ndcg.toFixed(2)} (judged in top9: ${r.m!.judgedInTop9})`);
      }
      expect(rows.length).toBeGreaterThan(0);
    }
  });
});
