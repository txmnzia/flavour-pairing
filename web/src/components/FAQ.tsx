import { useEffect } from "react";
import IngredientTile from "./IngredientTile";

function ScoreBadge({ value }: { value: number }) {
  const clamped = Math.min(Math.max(value, 0), 1);
  const pct = Math.round(clamped * 99);
  const radius = 14;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - clamped);
  const hue = Math.round(clamped * 120);
  const color = `hsl(${hue}, 85%, 55%)`;

  return (
    <div className="relative flex items-center justify-center shrink-0 w-9 h-9">
      <svg className="absolute inset-0 w-full h-full -rotate-90" viewBox="0 0 36 36">
        <circle cx="18" cy="18" r={radius} fill="rgba(0,0,0,0.55)" stroke="rgba(255,255,255,0.08)" strokeWidth="3" />
        {clamped > 0.01 && (
          <circle
            cx="18" cy="18" r={radius}
            fill="none" stroke={color} strokeWidth="3" strokeLinecap="round"
            strokeDasharray={circumference} strokeDashoffset={dashOffset}
          />
        )}
      </svg>
      <span className="relative z-10 font-bold text-white leading-none tabular-nums text-[10px]">
        {pct}
      </span>
    </div>
  );
}

function DemoCard({
  name, score, selected = false, outlier = false, label,
}: {
  name: string; score?: number; selected?: boolean; outlier?: boolean; label?: string;
}) {
  return (
    <div className="flex flex-col items-center gap-1.5">
      <div className={`
        flex flex-col rounded-xl overflow-hidden w-24
        ${selected && outlier
          ? "bg-red-600/20 border border-red-500/50"
          : selected
          ? "bg-brand-600/20 border border-brand-500/50"
          : "bg-white/5 border border-white/10"
        }
      `}>
        <IngredientTile name={name}>
          {score !== undefined && (
            <div className="absolute top-1.5 right-1.5">
              <ScoreBadge value={score} />
            </div>
          )}
          <div className={`
            absolute bottom-1.5 right-1.5 w-5 h-5 rounded-full flex items-center justify-center
            ${selected && outlier ? "bg-red-500/60" : selected ? "bg-brand-500/60" : "bg-white/10"}
          `}>
            {selected ? (
              <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg className="w-3 h-3 text-white/50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
            )}
          </div>
        </IngredientTile>
        <div className="px-2.5 py-2">
          <span className="text-xs text-white font-medium leading-tight">{name}</span>
        </div>
      </div>
      {label && (
        <span className="text-[11px] text-white/40 text-center">{label}</span>
      )}
    </div>
  );
}

export default function FAQ({ onClose, lang }: { onClose: () => void; lang: "en" | "fr" }) {
  const fr = lang === "fr";

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 bg-brand-900/95 backdrop-blur-sm overflow-y-auto"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="max-w-lg mx-auto px-4 py-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold">
            {fr ? "Comment ça fonctionne" : "How it works"}
          </h2>
          <button
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-full bg-white/10 hover:bg-white/20 transition-colors"
            aria-label="Close"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-8 text-sm">
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-white/50 mb-3">
              {fr ? "Données d'association" : "Pairing data"}
            </h3>
            <p className="text-white/70 leading-relaxed">
              {fr ? (
                <>
                  Les associations proviennent de <strong className="text-white">FlavorGraph</strong>, un jeu de données
                  scientifique construit en analysant la co-occurrence des ingrédients dans des centaines de milliers de
                  recettes. La force de chaque paire est mesurée par le{" "}
                  <strong className="text-white">NPMI</strong>{" "}
                  (information mutuelle ponctuelle normalisée) — un score statistique qui répond à la question :{" "}
                  <em>ces deux ingrédients apparaissent-ils ensemble bien plus souvent que par hasard ?</em>
                </>
              ) : (
                <>
                  Pairings come from <strong className="text-white">FlavorGraph</strong>, a scientific dataset built by
                  analysing which ingredients co-occur across hundreds of thousands of recipes. Each pair's strength
                  is measured by <strong className="text-white">NPMI</strong>{" "}
                  (Normalized Pointwise Mutual Information) — a statistical score that asks:{" "}
                  <em>do these two ingredients appear together significantly more often than chance?</em>
                </>
              )}
            </p>
            <p className="text-white/70 leading-relaxed mt-2">
              {fr
                ? "Le NPMI va de −1 (jamais ensemble) à +1 (toujours ensemble). Seules les paires avec un score de 0,01 ou plus sont conservées."
                : "NPMI ranges from −1 (never together) to +1 (always together). Only pairs scoring 0.01 or above are kept."}
            </p>
          </section>

          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-white/50 mb-3">
              {fr ? "Le score d'association" : "The pairing score"}
            </h3>
            <div className="flex gap-4 mb-4">
              <DemoCard name="lemon" score={0.84} label={fr ? "Fort (83)" : "Strong (83)"} />
              <DemoCard name="vanilla" score={0.49} label={fr ? "Moyen (49)" : "Moderate (49)"} />
              <DemoCard name="beef" score={0.13} label={fr ? "Faible (13)" : "Weak (13)"} />
            </div>
            <p className="text-white/70 leading-relaxed">
              {fr
                ? <>Le badge circulaire sur chaque carte affiche le score d'association sur une <strong className="text-white">échelle de 0 à 99</strong>, coloré du rouge (faible) au vert (fort).</>
                : <>The circular ring badge on each card shows the pairing score on a <strong className="text-white">0–99 scale</strong>, coloured from red (weak) to green (strong).</>}
            </p>
            <p className="text-white/70 leading-relaxed mt-2">
              {fr
                ? <>Avec plusieurs ingrédients sélectionnés, le score affiché est la <strong className="text-white">moyenne NPMI</strong> entre tous. Un candidat doit s'associer avec au moins la moitié de vos sélections pour apparaître.</>
                : <>With multiple ingredients selected, the score shown is the <strong className="text-white">average NPMI</strong> across all of them. A candidate must pair with at least half your selections to appear at all.</>}
            </p>
            <p className="text-white/70 leading-relaxed mt-2">
              {fr
                ? <>Les suggestions favorisent les <strong className="text-white">compléments</strong> : un candidat de la même famille qu'un ingrédient déjà sélectionné (une deuxième viande, une épice à côté d'une épice) est volontairement rétrogradé, et une association <strong className="text-white">exceptionnelle pour cet ingrédient</strong> passe devant une association banale.</>
                : <>Suggestions favour <strong className="text-white">complements</strong>: a candidate from the same family as something you already selected (a second meat, a spice next to a spice) is deliberately demoted, and a pairing that is <strong className="text-white">exceptional for that ingredient</strong> outranks a merely common one.</>}
            </p>
          </section>

          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-white/50 mb-3">
              {fr ? "Cartes sélectionnées et mise en évidence LOO" : "Selected cards & LOO highlighting"}
            </h3>
            <div className="flex gap-4 mb-4">
              <DemoCard name="garlic" score={0.74} selected label={fr ? "Bon accord" : "Good fit"} />
              <DemoCard name="chocolate" score={0.09} selected outlier label={fr ? "Mauvais accord" : "Poor fit"} />
            </div>
            <p className="text-white/70 leading-relaxed">
              {fr
                ? <>Une fois deux ingrédients ou plus sélectionnés, chaque carte affiche son <strong className="text-white">score LOO</strong> (Leave-One-Out) : la force d'association moyenne entre cet ingrédient et tous les autres de votre sélection.</>
                : <>Once you've selected two or more ingredients, each selected card shows its <strong className="text-white">LOO score</strong> (Leave-One-Out): the average pairing strength between that ingredient and every other ingredient in your selection.</>}
            </p>
            <p className="text-white/70 leading-relaxed mt-2">
              {fr
                ? <>Une carte devient <strong className="text-red-400">rouge</strong> lorsque son score LOO est à la fois plus d'un écart-type en dessous de la moyenne du groupe <em>et</em> inférieur à la moitié de cette moyenne. Cet ingrédient affaiblit la combinaison — le retirer améliorera l'harmonie globale.</>
                : <>A card turns <strong className="text-red-400">red</strong> when its LOO score is both more than one standard deviation below the group mean <em>and</em> below half the group mean. That ingredient is weakening the combination — removing it will improve overall harmony.</>}
            </p>
            <p className="text-white/70 leading-relaxed mt-2">
              {fr
                ? <>Le grand badge affiché au-dessus de la grille de sélection est le <strong className="text-white">score d'harmonie du groupe</strong> — la moyenne des scores LOO de tous les ingrédients sélectionnés.</>
                : <>The large badge shown above the selection grid is the <strong className="text-white">group harmony score</strong> — the mean LOO score across all selected ingredients.</>}
            </p>
          </section>
        </div>

        <div className="mt-8 pt-5 border-t border-white/10 text-center text-xs text-white/25 space-y-1">
          <div>{fr ? "Données : FlavorGraph (Apache 2.0)" : "Data: FlavorGraph (Apache 2.0)"}</div>
          <div>
            <a
              href={`${import.meta.env.BASE_URL}attributions.html`}
              target="_blank"
              rel="noreferrer"
              className="underline hover:text-white/50 transition-colors"
            >
              {fr ? "Crédits images" : "Image credits"}
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
