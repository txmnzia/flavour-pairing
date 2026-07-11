// Display names for taxonomy categories (swimlane headers, issue #52).
// Keys are the category slugs used in web/public/taxonomy.json.
const LABELS: Record<string, { en: string; fr: string }> = {
  vegetable: { en: "Vegetables", fr: "Légumes" },
  fruit: { en: "Fruits", fr: "Fruits" },
  herb: { en: "Herbs", fr: "Herbes" },
  spice: { en: "Spices", fr: "Épices" },
  meat: { en: "Meat", fr: "Viandes" },
  seafood: { en: "Seafood", fr: "Poissons & fruits de mer" },
  egg: { en: "Eggs", fr: "Œufs" },
  dairy: { en: "Dairy", fr: "Produits laitiers" },
  starch: { en: "Starches", fr: "Féculents" },
  "legume-nut": { en: "Legumes & nuts", fr: "Légumineuses & noix" },
  fat: { en: "Fats & oils", fr: "Matières grasses" },
  condiment: { en: "Condiments", fr: "Condiments" },
  sweet: { en: "Sweet", fr: "Sucré" },
  alcohol: { en: "Alcohol", fr: "Alcools" },
  beverage: { en: "Beverages", fr: "Boissons" },
  other: { en: "Other", fr: "Autres" },
};

export function categoryLabel(category: string, lang: "en" | "fr"): string {
  const entry = LABELS[category];
  if (entry) return entry[lang];
  return category.charAt(0).toUpperCase() + category.slice(1);
}
