// Discreet per-category tile background: a subtle hue lifted a few shades
// above the app's dark base (brand-900). Keys are taxonomy category slugs
// (see web/public/taxonomy.json and utils/categoryLabels.ts). Dairy is kept a
// touch lighter so it reads as "cream".
const CATEGORY_HSL: Record<string, string> = {
  vegetable: "140, 34%, 20%",
  herb: "96, 30%, 22%",
  fruit: "352, 40%, 24%",
  spice: "26, 46%, 23%",
  meat: "8, 40%, 20%",
  seafood: "190, 40%, 22%",
  egg: "44, 44%, 25%",
  dairy: "44, 16%, 34%",
  starch: "33, 28%, 28%",
  "legume-nut": "22, 36%, 20%",
  fat: "62, 32%, 22%",
  condiment: "250, 26%, 26%",
  sweet: "322, 34%, 25%",
  alcohol: "286, 28%, 26%",
  beverage: "208, 36%, 25%",
  other: "234, 14%, 21%",
};

export function categoryColor(category: string): string {
  return `hsl(${CATEGORY_HSL[category] ?? CATEGORY_HSL.other})`;
}
