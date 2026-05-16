import fr from "../translations/fr.json";

type Dict = Record<string, string>;
const dict = fr as Dict;

function lookup(name: string): string | null {
  return dict[name] ?? dict[name.toLowerCase()] ?? null;
}

// Common leading modifiers: "fresh garlic" → "ail frais"
const PREFIX_FR: Dict = {
  fresh: "frais", freshly: "fraîchement moulu",
  ground: "moulu", dried: "séché", frozen: "surgelé",
  minced: "émincé", chopped: "haché", sliced: "en tranches",
  shredded: "râpé", grated: "râpé", whole: "entier",
  cooked: "cuit", raw: "cru", canned: "en conserve",
  cold: "froid", warm: "chaud", hot: "chaud",
  unsalted: "non salé", salted: "salé", lean: "maigre",
  smoked: "fumé", pickled: "mariné", roasted: "rôti",
  toasted: "grillé", candied: "confit", grilled: "grillé",
  blanched: "blanchi", marinated: "mariné", organic: "bio",
  wild: "sauvage", baby: "jeune", large: "grand", small: "petit",
  sweet: "doux", sour: "aigre", spicy: "épicé", mild: "doux",
  extra: "extra", reduced: "réduit", instant: "instantané",
  powdered: "en poudre", crushed: "écrasé", peeled: "pelé",
  pitted: "dénoyauté", halved: "coupé en deux", softened: "ramolli",
  melted: "fondu", room: "température ambiante",
};

// Color modifiers: "red pepper" → "poivron rouge"
const COLOR_FR: Dict = {
  red: "rouge", green: "vert", black: "noir", white: "blanc",
  yellow: "jaune", golden: "doré", purple: "violet",
  orange: "orange", brown: "brun", pink: "rose", dark: "foncé",
  light: "léger",
};

// Trailing suffix patterns: "almond oil" → "huile d'amande"
type Fmt = (base: string) => string;
const SUFFIXES: Array<[string, Fmt]> = [
  [" oil",     (b) => /^[aeiouy]/i.test(b) ? `huile d'${b}` : `huile de ${b}`],
  [" juice",   (b) => /^[aeiouy]/i.test(b) ? `jus d'${b}` : `jus de ${b}`],
  [" seeds",   (b) => /^[aeiouy]/i.test(b) ? `graines d'${b}` : `graines de ${b}`],
  [" seed",    (b) => /^[aeiouy]/i.test(b) ? `graines d'${b}` : `graines de ${b}`],
  [" leaves",  (b) => /^[aeiouy]/i.test(b) ? `feuilles d'${b}` : `feuilles de ${b}`],
  [" leaf",    (b) => /^[aeiouy]/i.test(b) ? `feuille d'${b}` : `feuille de ${b}`],
  [" powder",  (b) => `${b} en poudre`],
  [" extract", (b) => /^[aeiouy]/i.test(b) ? `extrait d'${b}` : `extrait de ${b}`],
  [" flour",   (b) => /^[aeiouy]/i.test(b) ? `farine d'${b}` : `farine de ${b}`],
  [" vinegar", (b) => /^[aeiouy]/i.test(b) ? `vinaigre d'${b}` : `vinaigre de ${b}`],
  [" milk",    (b) => /^[aeiouy]/i.test(b) ? `lait d'${b}` : `lait de ${b}`],
  [" syrup",   (b) => /^[aeiouy]/i.test(b) ? `sirop d'${b}` : `sirop de ${b}`],
  [" paste",   (b) => /^[aeiouy]/i.test(b) ? `pâte d'${b}` : `pâte de ${b}`],
  [" butter",  (b) => /^[aeiouy]/i.test(b) ? `beurre d'${b}` : `beurre de ${b}`],
  [" cream",   (b) => /^[aeiouy]/i.test(b) ? `crème d'${b}` : `crème de ${b}`],
  [" broth",   (b) => /^[aeiouy]/i.test(b) ? `bouillon d'${b}` : `bouillon de ${b}`],
  [" stock",   (b) => /^[aeiouy]/i.test(b) ? `bouillon d'${b}` : `bouillon de ${b}`],
  [" sauce",   (b) => `sauce ${b}`],
  [" starch",  (b) => /^[aeiouy]/i.test(b) ? `fécule d'${b}` : `fécule de ${b}`],
  [" flakes",  (b) => /^[aeiouy]/i.test(b) ? `flocons d'${b}` : `flocons de ${b}`],
  [" chips",   (b) => `chips de ${b}`],
  [" spread",  (b) => `tartinade de ${b}`],
];

export function translateFr(name: string): string {
  // 1. Exact match
  const exact = lookup(name);
  if (exact) return exact;

  const lower = name.toLowerCase().trim();

  // 2. Strip a leading modifier, translate the rest, append modifier
  for (const [prefix, frMod] of Object.entries(PREFIX_FR)) {
    if (lower.startsWith(prefix + " ")) {
      const rest = name.slice(prefix.length + 1);
      const baseFr = lookup(rest);
      if (baseFr) return `${baseFr} ${frMod}`;
    }
  }

  // 3. Strip a color prefix
  for (const [color, frColor] of Object.entries(COLOR_FR)) {
    if (lower.startsWith(color + " ")) {
      const rest = name.slice(color.length + 1);
      const baseFr = lookup(rest);
      if (baseFr) return `${baseFr} ${frColor}`;
    }
  }

  // 4. Try plural/singular variant before suffix patterns
  const plural = lookup(lower + "s");
  if (plural) return plural;
  if (lower.endsWith("s")) {
    const singular = lookup(lower.slice(0, -1));
    if (singular) return singular;
  }

  // 5. Try suffix patterns
  for (const [suffix, fmt] of SUFFIXES) {
    if (lower.endsWith(suffix)) {
      const baseEn = name.slice(0, name.length - suffix.length);
      const baseFr = lookup(baseEn) ?? baseEn;
      return fmt(baseFr);
    }
  }

  // 6. Fall back to English
  return name;
}
