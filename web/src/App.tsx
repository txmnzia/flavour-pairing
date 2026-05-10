import { useState, useEffect, useMemo, useCallback } from "react";
import { loadDatabase, getAllIngredients, getAllCuisines, getRecommendations, getDataMeta, getRecipesForIngredients } from "./db";
import type { Ingredient, Cuisine, Pairing, DbStatus } from "./types";
import CuisineFilter from "./components/CuisineFilter";
import SearchInput from "./components/SearchInput";
import RecommendationList from "./components/RecommendationList";
import { translateFr } from "./utils/translateFr";

const TOP_N = 9;
const BROWSE_N = 30;

export default function App() {
  const [status, setStatus] = useState<DbStatus>({ state: "idle" });
  const [ingredients, setIngredients] = useState<Ingredient[]>([]);
  const [cuisines, setCuisines] = useState<Cuisine[]>([]);
  const [selectedIngredients, setSelectedIngredients] = useState<Ingredient[]>([]);
  const [selectedCuisine, setSelectedCuisine] = useState<Cuisine | null>(null);
  const [recommendations, setRecommendations] = useState<Pairing[]>([]);
  const [matchingRecipes, setMatchingRecipes] = useState<string[]>([]);
  const [dataMeta, setDataMeta] = useState<{ source: string; recipes: number } | null>(null);
  const [lang, setLang] = useState<"en" | "fr">("en");
  const [query, setQuery] = useState("");

  const translate = useCallback(
    (name: string) => lang === "fr" ? translateFr(name) : name,
    [lang]
  );

  useEffect(() => {
    setStatus({ state: "loading", progress: "Starting…" });
    loadDatabase((progress) => setStatus({ state: "loading", progress }))
      .then(() => {
        setIngredients(getAllIngredients());
        setCuisines(getAllCuisines());
        setDataMeta(getDataMeta());
        setStatus({ state: "ready" });
      })
      .catch((err) => {
        console.error(err);
        setStatus({ state: "error", message: String(err) });
      });
  }, []);

  useEffect(() => {
    if (status.state !== "ready" || selectedIngredients.length === 0) {
      setRecommendations([]);
      setMatchingRecipes([]);
      return;
    }
    const allCuisine = cuisines.find((c) => c.name === "all");
    const cuisineId = selectedCuisine?.id ?? allCuisine?.id ?? 1;
    const ids = selectedIngredients.map((i) => i.id);
    setRecommendations(getRecommendations(ids, ingredients, cuisineId, TOP_N));
    setMatchingRecipes(getRecipesForIngredients(ids));
  }, [selectedIngredients, selectedCuisine, status, ingredients, cuisines]);

  const selectedIds = useMemo(
    () => new Set(selectedIngredients.map((i) => i.id)),
    [selectedIngredients]
  );

  const maxFreq = useMemo(
    () => ingredients.reduce((m, i) => Math.max(m, i.freq), 1),
    [ingredients]
  );

  const browseIngredients = useMemo(() => {
    if (selectedIngredients.length > 0) return [];
    const q = query.toLowerCase().trim();
    return ingredients
      .filter((i) => {
        if (selectedIds.has(i.id)) return false;
        if (!q) return true;
        return translate(i.name).toLowerCase().includes(q);
      })
      .sort((a, b) => {
        if (query) {
          const aStart = translate(a.name).toLowerCase().startsWith(query.toLowerCase());
          const bStart = translate(b.name).toLowerCase().startsWith(query.toLowerCase());
          if (aStart !== bStart) return aStart ? -1 : 1;
        }
        return b.freq - a.freq;
      })
      .slice(0, BROWSE_N);
  }, [ingredients, selectedIngredients, selectedIds, query, translate]);

  const addIngredient = useCallback(
    (name: string) => {
      const ing = ingredients.find((i) => i.name === name);
      if (!ing || selectedIds.has(ing.id)) return;
      setSelectedIngredients((prev) => [...prev, ing]);
      setQuery("");
    },
    [ingredients, selectedIds]
  );

  const removeIngredient = useCallback((id: number) => {
    setSelectedIngredients((prev) => prev.filter((i) => i.id !== id));
  }, []);

  const isReady = status.state === "ready";
  const isBrowsing = selectedIngredients.length === 0;

  const footerLine = useMemo(() => {
    if (!isReady) return null;
    const ingCount = ingredients.length.toLocaleString();
    if (!dataMeta || dataMeta.source === "demo") {
      return `${ingCount} ingredients · Demo data`;
    }
    const recCount = dataMeta.recipes.toLocaleString();
    const src = dataMeta.source === "recipenlg" ? "RecipeNLG" : "RecipeNLG + Marmiton";
    return `Based on ${ingCount} ingredients from ${recCount} recipes · ${src}`;
  }, [isReady, ingredients, dataMeta]);

  return (
    <div className="min-h-screen bg-brand-900 text-white flex flex-col">
      <header className="border-b border-white/10 px-4 py-4 flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <span className="text-2xl" aria-hidden>🍳</span>
          <div>
            <h1 className="text-lg font-semibold leading-none">Flavour Pairing</h1>
            <p className="text-xs text-white/40 mt-0.5">
              Discover what goes well together
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isReady && (
            <CuisineFilter
              cuisines={cuisines}
              selected={selectedCuisine}
              onChange={setSelectedCuisine}
            />
          )}
          <button
            onClick={() => setLang((l) => (l === "en" ? "fr" : "en"))}
            className="text-lg px-2 py-1 rounded-lg bg-white/10 hover:bg-white/20 transition-colors leading-none"
            title={lang === "en" ? "Switch to French" : "Passer en anglais"}
          >
            {lang === "en" ? "🇫🇷" : "🇬🇧"}
          </button>
        </div>
      </header>

      <main className="flex-1 max-w-lg mx-auto w-full px-4 py-6 flex flex-col gap-6">
        {status.state === "loading" && (
          <div className="flex items-center gap-3 text-sm text-white/60">
            <svg className="w-4 h-4 animate-spin shrink-0" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {status.progress}
          </div>
        )}
        {status.state === "error" && (
          <div className="rounded-xl bg-red-500/20 border border-red-500/30 px-4 py-3 text-sm text-red-300">
            <strong>Failed to load data.</strong> {status.message}
          </div>
        )}

        <section>
          <SearchInput
            query={query}
            onQueryChange={setQuery}
            ingredients={ingredients}
            selectedIds={selectedIds}
            onSelect={(ing) => addIngredient(ing.name)}
            translate={translate}
            placeholder={
              isBrowsing
                ? (lang === "fr" ? "Rechercher un ingrédient…" : "Search an ingredient…")
                : (lang === "fr" ? "Ajouter un ingrédient…" : "Add an ingredient…")
            }
            disabled={!isReady}
            showDropdown={!isBrowsing}
          />
        </section>


        {isReady && (
          <section className="flex-1">
            {isBrowsing ? (
              <>
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs text-white/40 uppercase tracking-wider">
                    {query
                      ? (lang === "fr" ? "Résultats" : "Results")
                      : (lang === "fr" ? "Ingrédients populaires" : "Popular ingredients")}
                  </span>
                  <span className="text-xs text-white/30">
                    {lang === "fr" ? "appuyer pour sélectionner" : "tap to select"}
                  </span>
                </div>
                <RecommendationList
                  browseIngredients={browseIngredients}
                  maxFreq={maxFreq}
                  recommendations={[]}
                  selectedCount={0}
                  onAdd={addIngredient}
                  translate={translate}
                />
              </>
            ) : (
              <>
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs text-white/40 uppercase tracking-wider">
                    {lang === "fr" ? "Sélectionnés" : "Selected"}
                  </span>
                  <button
                    onClick={() => setSelectedIngredients([])}
                    className="text-xs text-white/30 hover:text-white/60 transition-colors"
                  >
                    {lang === "fr" ? "Tout effacer" : "Clear all"}
                  </button>
                </div>
                <RecommendationList
                  recommendations={recommendations}
                  selectedCount={selectedIngredients.length}
                  onAdd={addIngredient}
                  translate={translate}
                  selectedIngredients={selectedIngredients}
                  maxFreqSelected={maxFreq}
                  onRemove={removeIngredient}
                />

                {matchingRecipes.length > 0 && (
                  <div className="mt-6">
                    <div className="flex items-center gap-3 mb-3">
                      <div className="flex-1 h-px bg-white/10" />
                      <span className="text-xs text-white/30 uppercase tracking-wider shrink-0">
                        {lang === "fr" ? "Recettes" : "Recipes"}
                      </span>
                      <div className="flex-1 h-px bg-white/10" />
                    </div>
                    <ul className="space-y-2">
                      {matchingRecipes.map((title) => (
                        <li key={title} className="flex items-center gap-3 bg-white/5 border border-white/10 rounded-xl px-4 py-3">
                          <svg className="w-4 h-4 text-white/30 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                            <path strokeLinecap="round" strokeLinejoin="round"
                              d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
                          </svg>
                          <span className="text-sm text-white/70 capitalize">{title}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </section>
        )}
      </main>

      <footer className="text-center text-xs text-white/20 py-4 px-4 space-y-0.5">
        {footerLine && <div>{footerLine}</div>}
        <div>Ranked by co-occurrence (NPMI)</div>
      </footer>
    </div>
  );
}
