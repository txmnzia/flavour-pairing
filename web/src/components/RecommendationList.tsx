import { useState, useEffect } from "react";
import type { Ingredient, Pairing } from "../types";
import { getIngredientEmoji, getIngredientColor } from "../utils/ingredientEmoji";
import { sentenceCase } from "../utils/format";

const PAGE_SIZE = 9;

interface Props {
  recommendations: Pairing[];
  onAdd: (name: string) => void;
  translate: (name: string) => string;
  browseIngredients?: Ingredient[];
  selectedIngredients?: Ingredient[];
  onRemove?: (id: number) => void;
  looScores?: Map<number, number>;
}

function scoreToColor(value: number): string {
  const hue = Math.round(Math.min(Math.max(value, 0), 1) * 120);
  return `hsl(${hue}, 85%, 55%)`;
}

function ScoreBadge({ value, size = "sm" }: { value: number; size?: "sm" | "lg" }) {
  const clamped = Math.min(Math.max(value, 0), 1);
  const pct = Math.round(clamped * 99);
  const radius = 14;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - clamped);
  const color = scoreToColor(clamped);

  return (
    <div className={`relative flex items-center justify-center shrink-0 ${size === "lg" ? "w-12 h-12" : "w-9 h-9"}`}>
      <svg className="absolute inset-0 w-full h-full -rotate-90" viewBox="0 0 36 36">
        <circle cx="18" cy="18" r={radius} fill="rgba(0,0,0,0.55)" stroke="rgba(255,255,255,0.08)" strokeWidth="3" />
        {clamped > 0.01 && (
          <circle
            cx="18" cy="18" r={radius}
            fill="none"
            stroke={color}
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
          />
        )}
      </svg>
      <span className={`relative z-10 font-bold text-white leading-none tabular-nums ${size === "lg" ? "text-sm" : "text-[10px]"}`}>
        {pct}
      </span>
    </div>
  );
}

function Card({
  name, score, onClick, translate,
  selected = false, outlier = false,
}: {
  name: string; score?: number;
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
        {score !== undefined && (
          <div className="absolute top-1.5 right-1.5">
            <ScoreBadge value={score} />
          </div>
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
      <div className="px-2.5 py-2">
        <span className="text-xs text-white font-medium leading-tight line-clamp-2">
          {sentenceCase(translate(name))}
        </span>
      </div>
    </button>
  );
}

function PairingGrid({
  recommendations, onAdd, translate,
}: Pick<Props, "recommendations" | "onAdd" | "translate">) {
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
  if (mean < 0.05) return new Set();
  const std = Math.sqrt(vals.reduce((acc, v) => acc + (v - mean) ** 2, 0) / vals.length);
  const outliers = new Set<number>();
  for (const [id, score] of looScores) {
    if (score < mean - std && score < mean * 0.5) outliers.add(id);
  }
  return outliers;
}

export default function RecommendationList({
  recommendations, onAdd, translate,
  browseIngredients,
  selectedIngredients, onRemove, looScores,
}: Props) {
  if (browseIngredients && browseIngredients.length > 0) {
    return (
      <div className="grid grid-cols-3 gap-2.5">
        {browseIngredients.map((ing) => (
          <Card
            key={ing.id}
            name={ing.name}
            onClick={() => onAdd(ing.name)}
            translate={translate}
          />
        ))}
      </div>
    );
  }

  if (browseIngredients && browseIngredients.length === 0 && recommendations.length === 0 && !selectedIngredients?.length) {
    return (
      <p className="text-center text-white/30 text-sm py-12">
        {translate("No ingredients found")}
      </p>
    );
  }

  const outlierIds = looScores ? computeOutlierIds(looScores) : new Set<number>();
  const hasLooScores = looScores && looScores.size >= 2;

  const overallScore = hasLooScores
    ? [...looScores!.values()].reduce((a, b) => a + b, 0) / looScores!.size
    : null;

  const selectedGrid = selectedIngredients && selectedIngredients.length > 0 && onRemove ? (
    <div className="mb-5">
      {overallScore !== null && (
        <div className="flex items-center gap-3 mb-4">
          <ScoreBadge value={overallScore} size="lg" />
          <span className="text-xs text-white/40 uppercase tracking-wider">Group harmony</span>
        </div>
      )}
      <div className="grid grid-cols-3 gap-2.5">
        {selectedIngredients.map((ing) => {
          const isOutlier = outlierIds.has(ing.id);
          const looScore = hasLooScores ? looScores!.get(ing.id) : undefined;
          return (
            <Card
              key={ing.id}
              name={ing.name}
              score={looScore}
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
        onAdd={onAdd}
        translate={translate}
      />
    </>
  );
}
