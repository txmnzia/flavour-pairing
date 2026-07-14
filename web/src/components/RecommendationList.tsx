import { useState } from "react";
import type { CategoryLane, Ingredient } from "../types";
import IngredientTile from "./IngredientTile";
import { sentenceCase } from "../utils/format";
import { categoryLabel } from "../utils/categoryLabels";

interface Props {
  lanes: CategoryLane[];
  onAdd: (name: string) => void;
  translate: (name: string) => string;
  lang?: "en" | "fr";
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
        w-full flex flex-col rounded-xl overflow-hidden text-left
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
      <IngredientTile name={name}>
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
      </IngredientTile>
      <div className="px-2.5 py-2">
        <span className="text-xs text-white font-medium leading-tight line-clamp-2">
          {sentenceCase(translate(name))}
        </span>
      </div>
    </button>
  );
}

// One horizontally-scrollable row per ingredient category (issue #52).
// The -mx-4/px-4 bleed lets rows scroll edge-to-edge while headers stay
// aligned with the page padding; a partially visible card at the right edge
// is the scroll affordance.
function CategoryLanes({
  lanes, onAdd, translate, lang,
}: Pick<Props, "lanes" | "onAdd" | "translate" | "lang">) {
  return (
    <div className="space-y-5">
      {lanes.map((lane) => (
        <section key={lane.category} aria-label={categoryLabel(lane.category, lang ?? "en")}>
          <h3 className="text-xs text-white/40 uppercase tracking-wider mb-2">
            {categoryLabel(lane.category, lang ?? "en")}
          </h3>
          <div className="flex gap-2.5 overflow-x-auto -mx-4 px-4 lg:-mx-8 lg:px-8 pb-1 snap-x">
            {lane.pairings.map((pairing) => (
              <div key={pairing.ingredient.id} className="w-28 shrink-0 snap-start">
                <Card
                  name={pairing.ingredient.name}
                  score={pairing.score}
                  onClick={() => onAdd(pairing.ingredient.name)}
                  translate={translate}
                />
              </div>
            ))}
          </div>
        </section>
      ))}
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
  lanes, onAdd, translate, lang = "en",
  browseIngredients,
  selectedIngredients, onRemove, looScores,
}: Props) {
  const fr = lang === "fr";
  if (browseIngredients && browseIngredients.length > 0) {
    return (
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-7 xl:grid-cols-8 gap-2.5">
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

  if (browseIngredients && browseIngredients.length === 0 && lanes.length === 0 && !selectedIngredients?.length) {
    return (
      <p className="text-center text-white/30 text-sm py-12">
        {fr ? "Aucun ingrédient trouvé" : "No ingredients found"}
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
          <span className="text-xs text-white/40 uppercase tracking-wider">
            {fr ? "Harmonie du groupe" : "Group harmony"}
          </span>
        </div>
      )}
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-7 xl:grid-cols-8 gap-2.5">
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
        <span className="text-xs text-white/30 uppercase tracking-wider shrink-0">
          {fr ? "s'accorde bien avec" : "pairs well with"}
        </span>
        <div className="flex-1 h-px bg-white/10" />
      </div>
    </div>
  ) : null;

  if (lanes.length === 0) {
    return (
      <>
        {selectedGrid}
        <p className="text-center text-white/30 text-sm py-12">
          {fr
            ? "Aucune association trouvée — essayez un autre ingrédient"
            : "No pairings found — try a different ingredient"}
        </p>
      </>
    );
  }

  return (
    <>
      {selectedGrid}
      <CategoryLanes
        lanes={lanes}
        onAdd={onAdd}
        translate={translate}
        lang={lang}
      />
    </>
  );
}
