import { useState, useEffect } from "react";
import type { Ingredient, Pairing } from "../types";
import { getIngredientEmoji, getIngredientColor } from "../utils/ingredientEmoji";

const PAGE_SIZE = 9;

interface Props {
  recommendations: Pairing[];
  selectedCount: number;
  onAdd: (name: string) => void;
  translate: (name: string) => string;
  browseIngredients?: Ingredient[];
  maxFreq?: number;
  /** Selected ingredients to show as removable cards */
  selectedIngredients?: Ingredient[];
  maxFreqSelected?: number;
  onRemove?: (id: number) => void;
  looScores?: Map<number, number>;
}


function ScoreBar({ value, color }: { value: number; color?: string }) {
  const pct = Math.round(value * 100);
  const barColor = color ?? (
    value >= 0.6 ? "bg-emerald-400" :
    value >= 0.35 ? "bg-amber-400" : "bg-white/30"
  );

  return (
    <div className="flex items-center gap-1.5">
      <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${barColor}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <span className="text-xs text-white/40 tabular-nums w-6 text-right shrink-0">
        {pct}
      </span>
    </div>
  );
}

function CoverageBadge({ coverage, total }: { coverage: number; total: number }) {
  if (total <= 1 || coverage === total) return null;
  return (
    <span className="absolute top-1.5 right-1.5 text-xs px-1.5 py-0.5 rounded-full bg-black/50 text-white/50 leading-none">
      {coverage}/{total}
    </span>
  );
}

function Card({
  name, score, scoreColor, coverage, totalSelected, onClick, translate,
  selected = false, outlier = false,
}: {
  name: string; score: number; scoreColor?: string;
  coverage?: number; totalSelected?: number;
  onClick: () => void; translate: (n: string) => string;
  selected?: boolean; outlier?: boolean;
}) {
  const [hovered, setHovered] = useState(false);

  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className={`
        flex flex-col rounded-xl overflow-hidden text-left
        transition-all duration-150
        ${selected && outlier
          ? hovered
            ? "bg-red-600/30 border border-red-400/70"
            : "bg-red-600/20 border border-red-500/50"
          : selected
          ? hovered
            ? "bg-brand-600/30 border border-brand-400/70"
            : "bg-brand-600/20 border border-brand-500/50"
          : hovered
          ? "bg-white/10 border border-white/20"
          : "bg-white/5 border border-white/10 active:bg-white/15"
        }
      `}
    >
      <div
        className="relative w-full aspect-square flex items-center justify-center"
        style={{ background: getIngredientColor(name) }}
      >
        <span className="text-3xl select-none" role="img" aria-label={name}>
          {getIngredientEmoji(name)}
        </span>
        {coverage !== undefined && totalSelected !== undefined && (
          <CoverageBadge coverage={coverage} total={totalSelected} />
        )}
        <div className={`
          absolute bottom-1.5 right-1.5
          w-5 h-5 rounded-full flex items-center justify-center
          transition-colors
          ${selected && outlier
            ? hovered ? "bg-red-500" : "bg-red-500/60"
            : selected
            ? hovered ? "bg-red-500" : "bg-brand-500/60"
            : hovered ? "bg-brand-500" : "bg-white/10"
          }
        `}>
          {selected ? (
            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          ) : (
            <svg className={`w-3 h-3 transition-colors ${hovered ? "text-white" : "text-white/50"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
          )}
        </div>
      </div>
      <div className="px-2.5 pt-2 pb-2.5 flex flex-col justify-between flex-1 gap-1.5">
        <span className="text-xs text-white font-medium leading-tight line-clamp-2">
          {translate(name)}
        </span>
        <ScoreBar value={score} color={scoreColor} />
      </div>
    </button>
  );
}

function PairingGrid({
  recommendations, selectedCount, onAdd, translate,
}: Pick<Props, "recommendations" | "selectedCount" | "onAdd" | "translate">) {
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [recommendations]);

  const visible = recommendations.slice(0, visibleCount);
  const hasMore = visibleCount < recommendations.length;

  return (
    <div>
      <div className="grid grid-cols-3 gap-2.5">
        {visible.map((pairing) => (
          <Card
            key={pairing.ingredient.id}
            name={pairing.ingredient.name}
            score={pairing.score}
            coverage={pairing.coverage}
            totalSelected={selectedCount}
            onClick={() => onAdd(pairing.ingredient.name)}
            translate={translate}
          />
        ))}
      </div>

      {hasMore && (
        <button
          onClick={() => setVisibleCount((n) => n + PAGE_SIZE)}
          className="mt-4 w-full flex flex-col items-center gap-1 text-xs text-white/30 hover:text-white/60 transition-colors py-1"
          aria-label="Show more"
        >
          <span>more</span>
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      )}
    </div>
  );
}

function computeOutlierIds(looScores: Map<number, number>): Set<number> {
  if (looScores.size < 2) return new Set();
  const vals = [...looScores.values()];
  const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
  // If the whole group has no meaningful pairing signal, nothing to flag.
  if (mean < 0.05) return new Set();
  const std = Math.sqrt(vals.reduce((acc, v) => acc + (v - mean) ** 2, 0) / vals.length);
  const outliers = new Set<number>();
  for (const [id, score] of looScores) {
    // Flag if > 1 std dev below mean AND less than half the group average.
    // Missing pairings return 0 (not negative), so we cannot rely on score < 0.
    if (score < mean - std && score < mean * 0.5) outliers.add(id);
  }
  return outliers;
}

export default function RecommendationList({
  recommendations, selectedCount, onAdd, translate,
  browseIngredients, maxFreq = 1,
  selectedIngredients, maxFreqSelected = 1, onRemove, looScores,
}: Props) {
  if (browseIngredients && browseIngredients.length > 0) {
    return (
      <div className="grid grid-cols-3 gap-2.5">
        {browseIngredients.map((ing) => (
          <Card
            key={ing.id}
            name={ing.name}
            score={ing.freq / maxFreq}
            scoreColor="bg-brand-400"
            onClick={() => onAdd(ing.name)}
            translate={translate}
          />
        ))}
      </div>
    );
  }

  if (browseIngredients && browseIngredients.length === 0 && recommendations.length === 0 && selectedCount === 0) {
    return (
      <p className="text-center text-white/30 text-sm py-12">
        {translate("No ingredients found")}
      </p>
    );
  }

  const outlierIds = looScores ? computeOutlierIds(looScores) : new Set<number>();

  const selectedGrid = selectedIngredients && selectedIngredients.length > 0 && onRemove ? (
    <div className="mb-5">
      <div className="grid grid-cols-3 gap-2.5">
        {selectedIngredients.map((ing) => {
          const isOutlier = outlierIds.has(ing.id);
          return (
            <Card
              key={ing.id}
              name={ing.name}
              score={ing.freq / maxFreqSelected}
              scoreColor={isOutlier ? "bg-red-400" : "bg-brand-400"}
              selected
              outlier={isOutlier}
              onClick={() => onRemove(ing.id)}
              translate={translate}
            />
          );
        })}
      </div>
      <div className="mt-5 mb-3 flex items-center gap-3">
        <div className="flex-1 h-px bg-white/10" />
        <span className="text-xs text-white/30 uppercase tracking-wider shrink-0">pairs well with</span>
        <div className="flex-1 h-px bg-white/10" />
      </div>
    </div>
  ) : null;

  if (recommendations.length === 0) {
    return (
      <>
        {selectedGrid}
        <p className="text-center text-white/30 text-sm py-12">
          {translate("No pairings found — try a different ingredient")}
        </p>
      </>
    );
  }

  return (
    <>
      {selectedGrid}
      <PairingGrid
        recommendations={recommendations}
        selectedCount={selectedCount}
        onAdd={onAdd}
        translate={translate}
      />
    </>
  );
}
