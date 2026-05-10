import { useState, useEffect, useMemo, useCallback } from "react";
import { loadDatabase, getAllIngredients, getAllCuisines, getRecommendations, getDataMeta } from "./db";
import type { Ingredient, Cuisine, Pairing, DbStatus } from "./types";
import CuisineFilter from "./components/CuisineFilter";
import IngredientChip from "./components/IngredientChip";
import SearchInput from "./components/SearchInput";
import RecommendationList from "./components/RecommendationList";
import { translateFr } from "./utils/translateFr";

const TOP_N = 30;
const BROWSE_N = 30;

export default function App() {
  const [status, setStatus] = useState<DbStatus>({ state: "idle" });
  const [ingredients, setIngredients] = useState<Ingredient[]>([]);
  const [cuisines, setCuisines] = useState<Cuisine[]>([]);
  const [selectedIngredients, setSelectedIngredients] = useState<Ingredient[]>([]);
  const [selectedCuisine, setSelectedCuisine] = useState<Cuisine | null>(null);
  const [recommendations, setRecommendations] = useState<Pairing[]>([]);
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
      return;
    }
    const allCuisine = cuisines.find((c) => c.name === "all");
    const cuisineId = selectedCuisine?.id ?? allCuisine?.id ?? 1;
    const ids = selectedIngredients.map((i) => i.id);
    setRecommendations(getRecommendations(ids, ingredients, cuisineId, TOP_N));
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

        {selectedIngredients.length > 0 && (
          <section>
            <div className="flex items-center justify-between mb-2">
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
            <div className="flex flex-wrap gap-2">
              {selectedIngredients.map((ing) => (
                <IngredientChip
                  key={ing.id}
                  name={translate(ing.name)}
                  onRemove={() => removeIngredient(ing.id)}
                />
              ))}
            </div>
          </section>
        )}

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
                    {lang === "fr" ? "Se marie bien avec" : "Pairs well with"}
                  </span>
                  <span className="text-xs text-white/30">
                    {lang === "fr" ? "appuyer pour ajouter" : "tap to add"}
                  </span>
                </div>
                <RecommendationList
                  recommendations={recommendations}
                  selectedCount={selectedIngredients.length}
                  onAdd={addIngredient}
                  translate={translate}
                />
              </>
            )}
          </section>
        )}
      </main>

      <footer className="text-center text-xs text-white/20 py-4 px-4 space-y-0.5">
        {dataMeta ? (
          <>
            <div>
              {dataMeta.source === "demo" && "Demo data · not based on real recipes"}
              {dataMeta.source === "recipenlg" && `Based on ${(dataMeta.recipes / 1_000_000).toFixed(1)}M recipes · RecipeNLG dataset`}
              {dataMeta.source === "recipenlg+marmiton" && `Based on ${(dataMeta.recipes / 1_000_000).toFixed(1)}M recipes · RecipeNLG + Marmiton`}
            </div>
            <div>Ranked by co-occurrence (NPMI)</div>
          </>
        ) : (
          <div>Ranked by co-occurrence (NPMI)</div>
        )}
      </footer>
    </div>
  );
}
