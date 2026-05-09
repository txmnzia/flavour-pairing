import type { Pairing } from "../types";

interface Props {
  recommendations: Pairing[];
  selectedCount: number;
  onAdd: (name: string) => void;
  translate: (name: string) => string;
}

function ScoreBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    value >= 0.6 ? "bg-emerald-400" :
    value >= 0.35 ? "bg-amber-400" : "bg-white/30";

  return (
    <div className="flex items-center gap-2 min-w-0">
      <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${color}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <span className="text-xs text-white/40 tabular-nums w-8 text-right shrink-0">
        {pct}
      </span>
    </div>
  );
}

function CoverageTag({ coverage, total }: { coverage: number; total: number }) {
  if (total <= 1 || coverage === total) return null;
  return (
    <span className="text-xs px-1.5 py-0.5 rounded-full shrink-0 bg-white/10 text-white/40">
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
    <ul className="space-y-1.5">
      {recommendations.map((pairing) => (
        <li key={pairing.ingredient.id}>
          <button
            onClick={() => onAdd(pairing.ingredient.name)}
            className="
              w-full flex items-center gap-3 px-4 py-3 rounded-xl
              bg-white/5 hover:bg-white/10 active:bg-white/15
              border border-white/10 hover:border-white/20
              transition-all duration-150 text-left group
            "
          >
            <span className="flex-1 text-sm text-white capitalize truncate group-hover:text-white">
              {translate(pairing.ingredient.name)}
            </span>

            <CoverageTag coverage={pairing.coverage} total={selectedCount} />

            <div className="w-24 shrink-0">
              <ScoreBar value={pairing.npmi} />
            </div>

            <svg
              className="w-4 h-4 text-white/20 group-hover:text-brand-400 transition-colors shrink-0"
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
          </button>
        </li>
      ))}
    </ul>
  );
}
