interface Props {
  name: string;
  onRemove: () => void;
}

export default function IngredientChip({ name, onRemove }: Props) {
  return (
    <span className="
      inline-flex items-center gap-1.5 px-3 py-1
      bg-brand-600 text-white text-sm font-medium rounded-full
      select-none
    ">
      {name}
      <button
        onClick={onRemove}
        aria-label={`Remove ${name}`}
        className="
          w-4 h-4 rounded-full flex items-center justify-center
          text-white/70 hover:text-white hover:bg-white/20
          transition-colors focus:outline-none focus:ring-1 focus:ring-white/50
        "
      >
        <svg viewBox="0 0 12 12" fill="currentColor" className="w-2.5 h-2.5">
          <path d="M1 1l10 10M11 1L1 11" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
        </svg>
      </button>
    </span>
  );
}
