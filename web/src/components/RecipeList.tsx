import type { RecipeMatch } from "../db";
import { sentenceCase } from "../utils/format";

interface Props {
  matches: RecipeMatch[];
  lang: "en" | "fr";
  translate: (name: string) => string;
  loading: boolean;
}

// Pairing-fit badge for a leftover ingredient (thresholds calibrated on the NPMI
// data — see pairingFit in db.ts). Colour + short label so you can judge at a
// glance how well a selected-but-unused ingredient would fit the dish.
function fitBadge(fit: number, lang: "en" | "fr"): { cls: string; label: string } {
  if (fit >= 0.25) return { cls: "bg-emerald-400", label: lang === "fr" ? "excellent" : "great" };
  if (fit >= 0.1) return { cls: "bg-amber-400", label: lang === "fr" ? "bon" : "good" };
  return { cls: "bg-white/30", label: lang === "fr" ? "faible" : "weak" };
}

// Recipe suggestions for the current selection (issue #56). Each card links out
// to the source recipe, shows which selected ingredients it already uses, and —
// for the ones it doesn't — how well they'd pair with the dish, so you can both
// pick a recipe and judge customising it. `loading` covers the window where the
// selection is large enough but the (lazily fetched) corpus has not arrived yet.
export default function RecipeList({ matches, lang, translate, loading }: Props) {
  if (!loading && matches.length === 0) return null;

  const approximate = matches.length > 0 && matches.every((m) => m.approximate);

  return (
    <div className="mt-6">
      <div className="flex items-center gap-3 mb-3">
        <div className="flex-1 h-px bg-white/10" />
        <span className="text-xs text-white/30 uppercase tracking-wider shrink-0">
          {lang === "fr" ? "Recettes" : "Recipes"}
        </span>
        <div className="flex-1 h-px bg-white/10" />
      </div>

      {approximate && (
        <p className="text-xs text-white/40 mb-3">
          {lang === "fr"
            ? "Aucune recette ne réunit toute la sélection — voici les plus proches."
            : "No recipe uses your whole selection — here are the closest matches."}
        </p>
      )}

      {loading && matches.length === 0 ? (
        <div className="flex items-center gap-2 text-sm text-white/40 px-1 py-2">
          <svg className="w-4 h-4 animate-spin shrink-0" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          {lang === "fr" ? "Chargement des recettes…" : "Loading recipes…"}
        </div>
      ) : (
        <ul className="space-y-2">
          {matches.map((m) => (
            <li
              key={m.url || m.title}
              className="bg-white/5 border border-white/10 rounded-xl px-4 py-3"
            >
              <div className="flex items-start gap-3">
                <svg className="w-4 h-4 text-white/30 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round"
                    d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
                </svg>
                <div className="min-w-0 flex-1">
                  {m.url ? (
                    <a
                      href={m.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-white/80 hover:text-white underline decoration-white/20 hover:decoration-white/60 underline-offset-2"
                    >
                      {sentenceCase(m.title)}
                    </a>
                  ) : (
                    <span className="text-sm text-white/80">{sentenceCase(m.title)}</span>
                  )}
                  {m.used.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                      <span className="text-[11px] text-white/30 uppercase tracking-wide">
                        {lang === "fr" ? "Utilise" : "Uses"}
                      </span>
                      {m.used.map((name) => (
                        <span
                          key={name}
                          className="text-[11px] bg-white/10 text-white/60 rounded-full px-2 py-0.5"
                        >
                          {translate(name)}
                        </span>
                      ))}
                      {m.missing > 0 && (
                        <span className="text-[11px] text-white/30">
                          {lang === "fr"
                            ? `+${m.missing} ingrédient${m.missing > 1 ? "s" : ""}`
                            : `+${m.missing} ingredient${m.missing > 1 ? "s" : ""}`}
                        </span>
                      )}
                    </div>
                  )}
                  {m.suggested.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                      <span className="text-[11px] text-white/30 uppercase tracking-wide">
                        {lang === "fr" ? "À ajouter" : "Add"}
                      </span>
                      {m.suggested.map(({ name, fit }) => {
                        const b = fitBadge(fit, lang);
                        return (
                          <span
                            key={name}
                            className="inline-flex items-center gap-1.5 text-[11px] bg-white/5 border border-white/10 text-white/70 rounded-full px-2 py-0.5"
                            title={lang === "fr" ? "Compatibilité avec la recette" : "How well it pairs with this recipe"}
                          >
                            {translate(name)}
                            <span className={`w-1.5 h-1.5 rounded-full ${b.cls}`} aria-hidden />
                            <span className="text-white/40">{b.label}</span>
                          </span>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
