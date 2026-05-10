import type { Pairing } from "../types";

interface Props {
  recommendations: Pairing[];
  selectedCount: number;
  onAdd: (name: string) => void;
  translate: (name: string) => string;
}

function IngredientIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.2} className="w-10 h-10 text-white/20">
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M12 2C10.5 4.5 9 7.5 9 10a3 3 0 006 0c0-2.5-1.5-5.5-3-8z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 13v7" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.5 16.5q2.5 1 5 0" />
    </svg>
  );
}

function ScoreBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    value >= 0.6 ? "bg-emerald-400" :
    value >= 0.35 ? "bg-amber-400" : "bg-white/30";

  return (
    <div className="flex items-center gap-1.5">
      <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${color}`}
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

export default function RecommendationList({ recommendations, selectedCount, onAdd, translate }: Props) {
  if (recommendations.length === 0) {
    return (
      <p className="text-center text-white/30 text-sm py-12">
        {selectedCount === 0
          ? translate("Add an ingredient above to see pairings")
          : translate("No pairings found — try a different cuisine or ingredient")}
      </p>
    );
  }

  return (
    <div className="grid grid-cols-3 gap-2.5">
      {recommendations.map((pairing) => (
        <button
          key={pairing.ingredient.id}
          onClick={() => onAdd(pairing.ingredient.name)}
          className="
            flex flex-col rounded-xl overflow-hidden text-left
            bg-white/5 border border-white/10
            hover:bg-white/10 hover:border-white/20
            active:bg-white/15
            transition-all duration-150 group
          "
        >
          {/* Image area */}
          <div className="relative w-full aspect-square bg-white/5 flex items-center justify-center">
            <IngredientIcon />
            <CoverageBadge coverage={pairing.coverage} total={selectedCount} />
            {/* Add affordance */}
            <div className="
              absolute bottom-1.5 right-1.5
              w-5 h-5 rounded-full flex items-center justify-center
              bg-white/10 group-hover:bg-brand-500
              transition-colors
            ">
              <svg className="w-3 h-3 text-white/50 group-hover:text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
            </div>
          </div>

          {/* Name + score */}
          <div className="px-2.5 pt-2 pb-2.5 flex flex-col gap-1.5">
            <span className="text-xs text-white font-medium capitalize leading-tight line-clamp-2">
              {translate(pairing.ingredient.name)}
            </span>
            <ScoreBar value={pairing.npmi} />
          </div>
        </button>
      ))}
    </div>
  );
}
