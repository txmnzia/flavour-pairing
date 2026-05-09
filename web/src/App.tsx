import { useState, useEffect, useMemo, useCallback } from "react";
import { loadDatabase, getAllIngredients, getAllCuisines, getRecommendations } from "./db";
import type { Ingredient, Cuisine, Pairing, DbStatus } from "./types";
import CuisineFilter from "./components/CuisineFilter";
import IngredientChip from "./components/IngredientChip";
import SearchInput from "./components/SearchInput";
import RecommendationList from "./components/RecommendationList";

const TOP_N = 30;

export default function App() {
  const [status, setStatus] = useState<DbStatus>({ state: "idle" });
  const [ingredients, setIngredients] = useState<Ingredient[]>([]);
  const [cuisines, setCuisines] = useState<Cuisine[]>([]);
  const [selectedIngredients, setSelectedIngredients] = useState<Ingredient[]>([]);
  const [selectedCuisine, setSelectedCuisine] = useState<Cuisine | null>(null);
  const [recommendations, setRecommendations] = useState<Pairing[]>([]);

  // Boot: load DB
  useEffect(() => {
    setStatus({ state: "loading", progress: "Starting…" });
    loadDatabase((progress) => setStatus({ state: "loading", progress }))
      .then(() => {
        setIngredients(getAllIngredients());
        setCuisines(getAllCuisines());
        setStatus({ state: "ready" });
      })
      .catch((err) => {
        console.error(err);
        setStatus({ state: "error", message: String(err) });
      });
  }, []);

  // Recompute recommendations whenever selections change
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

  const addIngredient = useCallback(
    (name: string) => {
      const ing = ingredients.find((i) => i.name === name);
      if (!ing || selectedIds.has(ing.id)) return;
      setSelectedIngredients((prev) => [...prev, ing]);
    },
    [ingredients, selectedIds]
  );

  const removeIngredient = useCallback((id: number) => {
    setSelectedIngredients((prev) => prev.filter((i) => i.id !== id));
  }, []);

  const isReady = status.state === "ready";

  return (
    <div className="min-h-screen bg-brand-900 text-white flex flex-col">
      {/* Header */}
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
        {isReady && (
          <CuisineFilter
            cuisines={cuisines}
            selected={selectedCuisine}
            onChange={setSelectedCuisine}
          />
        )}
      </header>

      <main className="flex-1 max-w-lg mx-auto w-full px-4 py-6 flex flex-col gap-6">
        {/* Status banner */}
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

        {/* Search */}
        <section>
          <SearchInput
            ingredients={ingredients}
            selectedIds={selectedIds}
            onSelect={(ing) => addIngredient(ing.name)}
            disabled={!isReady}
          />
        </section>

        {/* Selected chips */}
        {selectedIngredients.length > 0 && (
          <section>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-white/40 uppercase tracking-wider">Selected</span>
              <button
                onClick={() => setSelectedIngredients([])}
                className="text-xs text-white/30 hover:text-white/60 transition-colors"
              >
                Clear all
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {selectedIngredients.map((ing) => (
                <IngredientChip
                  key={ing.id}
                  name={ing.name}
                  onRemove={() => removeIngredient(ing.id)}
                />
              ))}
            </div>
          </section>
        )}

        {/* Recommendations */}
        {isReady && (
          <section className="flex-1">
            {selectedIngredients.length > 0 && (
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs text-white/40 uppercase tracking-wider">
                  Pairs well with
                </span>
                <span className="text-xs text-white/30">
                  tap to add
                </span>
              </div>
            )}
            <RecommendationList
              recommendations={recommendations}
              selectedCount={selectedIngredients.length}
              onAdd={addIngredient}
            />
          </section>
        )}
      </main>

      {/* Footer */}
      <footer className="text-center text-xs text-white/20 py-4 px-4">
        Scores based on recipe co-occurrence (NPMI)
        {selectedCuisine && ` · ${selectedCuisine.name} cuisine`}
      </footer>
    </div>
  );
}
