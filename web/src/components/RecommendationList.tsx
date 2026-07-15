import { useState, useEffect, useRef } from "react";
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
  // True while pairings for the current selection are still being computed.
  computing?: boolean;
}

function scoreToColor(value: number): string {
  const hue = Math.round(Math.min(Math.max(value, 0), 1) * 120);
  return `hsl(${hue}, 85%, 55%)`;
}

const prefersReducedMotion = () =>
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// When `animate` is set, the ring sweeps and the number counts up from the
// previously-shown value to the new one whenever the score is (re)computed —
// the "affinity computed" feedback. Static (animate=false) elsewhere.
function ScoreBadge({ value, size = "sm", animate = false }: { value: number; size?: "sm" | "lg"; animate?: boolean }) {
  const target = Math.min(Math.max(value, 0), 1);
  const [display, setDisplay] = useState(animate ? 0 : target);
  const fromRef = useRef(0);

  useEffect(() => {
    if (!animate || prefersReducedMotion()) {
      setDisplay(target);
      fromRef.current = target;
      return;
    }
    const from = fromRef.current;
    const start = performance.now();
    const duration = 650;
    let raf = 0;
    const step = (now: number) => {
      const t = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3); // easeOutCubic
      setDisplay(from + (target - from) * eased);
      if (t < 1) raf = requestAnimationFrame(step);
      else fromRef.current = target;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, animate]);

  const shown = Math.min(Math.max(display, 0), 1);
  const pct = Math.round(shown * 99);
  const radius = 14;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - shown);
  const color = scoreToColor(shown);

  return (
    <div className={`relative flex items-center justify-center shrink-0 ${size === "lg" ? "w-12 h-12" : "w-9 h-9"}`}>
      <svg className="absolute inset-0 w-full h-full -rotate-90" viewBox="0 0 36 36">
        <circle cx="18" cy="18" r={radius} fill="rgba(0,0,0,0.55)" stroke="rgba(255,255,255,0.08)" strokeWidth="3" />
        {shown > 0.01 && (
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
  selected = false, outlier = false, enter = false, animateScore = false,
}: {
  name: string; score?: number;
  onClick: () => void; translate: (n: string) => string;
  selected?: boolean; outlier?: boolean; enter?: boolean; animateScore?: boolean;
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
        ${enter ? "motion-safe:animate-pop-in" : ""}
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
            <ScoreBadge value={score} animate={animateScore} />
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
      {/* Fixed height so 1- and 2-line labels produce equal-height tiles. */}
      <div className="px-2.5 py-2 min-h-[2.9rem]">
        <span className="text-xs text-white font-medium leading-tight line-clamp-2">
          {sentenceCase(translate(name))}
        </span>
      </div>
    </button>
  );
}

// One horizontally-scrollable row per ingredient category (issue #52).
// Cards sit in the normal content box so the first card lines up with the
// section headers and the selected-ingredient grid. Each card is sized to show
// exactly N per view (3 on mobile, scaling up with the grid columns) and the
// row is snap-mandatory, so scrolling always rests on whole tiles — never a
// half-tile at the edge.
const INITIAL_LANES = 3;
const LANE_STEP = 3;

function CategoryLanes({
  lanes, onAdd, translate, lang,
}: Pick<Props, "lanes" | "onAdd" | "translate" | "lang">) {
  // Progressive mount: render the first lanes immediately, then reveal the rest
  // over subsequent animation frames. A selection can produce ~16 lanes / ~170
  // cards; mounting them all in one task blocks the main thread for seconds on
  // mobile. The later lanes are below the fold, so filling them in over the next
  // few frames is invisible but keeps the first paint fast and the UI responsive.
  const [shown, setShown] = useState(INITIAL_LANES);
  const lanesRef = useRef(lanes);
  if (lanesRef.current !== lanes) {
    // New selection → restart the reveal from the top (adjusting state during
    // render is the supported way to reset when a prop changes).
    lanesRef.current = lanes;
    setShown(INITIAL_LANES);
  }
  useEffect(() => {
    if (shown >= lanes.length) return;
    const id = requestAnimationFrame(() =>
      setShown((s) => Math.min(s + LANE_STEP, lanes.length))
    );
    return () => cancelAnimationFrame(id);
  }, [shown, lanes.length]);

  return (
    <div className="space-y-5">
      {lanes.slice(0, shown).map((lane) => (
        <section key={lane.category} aria-label={categoryLabel(lane.category, lang ?? "en")}>
          <h3 className="text-xs text-white/40 uppercase tracking-wider mb-2">
            {categoryLabel(lane.category, lang ?? "en")}
          </h3>
          <div className="flex gap-2.5 overflow-x-auto pb-1 snap-x snap-mandatory">
            {lane.pairings.map((pairing) => (
              <div
                key={pairing.ingredient.id}
                className="shrink-0 snap-start w-[calc((100%_-_1.25rem)_/_3)] sm:w-[calc((100%_-_1.875rem)_/_4)] lg:w-[calc((100%_-_3.125rem)_/_6)] 2xl:w-[calc((100%_-_4.375rem)_/_8)]"
              >
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
  selectedIngredients, onRemove, looScores, computing = false,
}: Props) {
  const fr = lang === "fr";
  if (browseIngredients && browseIngredients.length > 0) {
    return (
      <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 2xl:grid-cols-8 gap-2.5">
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
          <ScoreBadge value={overallScore} size="lg" animate />
          <span className="text-xs text-white/40 uppercase tracking-wider">
            {fr ? "Harmonie du groupe" : "Group harmony"}
          </span>
        </div>
      )}
      <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 2xl:grid-cols-8 gap-2.5">
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
              enter
              animateScore
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
        {computing ? (
          <div className="flex items-center justify-center gap-3 text-sm text-white/50 py-12">
            <svg className="w-4 h-4 animate-spin shrink-0" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {fr ? "Recherche des associations…" : "Finding pairings…"}
          </div>
        ) : (
          <p className="text-center text-white/30 text-sm py-12">
            {fr
              ? "Aucune association trouvée — essayez un autre ingrédient"
              : "No pairings found — try a different ingredient"}
          </p>
        )}
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
