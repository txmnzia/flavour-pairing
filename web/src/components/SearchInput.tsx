import { useState, useRef, useEffect, useId, useMemo } from "react";
import type { Ingredient } from "../types";

interface Props {
  query: string;
  onQueryChange: (q: string) => void;
  ingredients: Ingredient[];
  selectedIds: Set<number>;
  onSelect: (ingredient: Ingredient) => void;
  translate: (name: string) => string;
  placeholder?: string;
  disabled?: boolean;
  /** When false (browse mode), suppress the dropdown — the card grid below handles it */
  showDropdown?: boolean;
}

const MAX_SUGGESTIONS = 8;

export default function SearchInput({
  query, onQueryChange,
  ingredients, selectedIds, onSelect, translate,
  placeholder, disabled,
  showDropdown = true,
}: Props) {
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listId = useId();

  const suggestions = useMemo(() => {
    if (!showDropdown || query.length === 0) return [];
    const q = query.toLowerCase();
    return ingredients
      .filter((i) => {
        if (selectedIds.has(i.id)) return false;
        return translate(i.name).toLowerCase().includes(q);
      })
      .sort((a, b) => {
        const aName = translate(a.name).toLowerCase();
        const bName = translate(b.name).toLowerCase();
        const aPrefix = aName.startsWith(query.toLowerCase());
        const bPrefix = bName.startsWith(query.toLowerCase());
        if (aPrefix !== bPrefix) return aPrefix ? -1 : 1;
        return b.freq - a.freq;
      })
      .slice(0, MAX_SUGGESTIONS);
  }, [ingredients, selectedIds, query, translate, showDropdown]);

  const dropdownVisible = showDropdown && open && suggestions.length > 0;

  useEffect(() => { setActiveIdx(-1); }, [query]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (!dropdownVisible) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, -1));
    } else if (e.key === "Enter" && activeIdx >= 0) {
      e.preventDefault();
      commit(suggestions[activeIdx]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  function commit(ingredient: Ingredient) {
    onSelect(ingredient);
    setOpen(false);
    setActiveIdx(-1);
    inputRef.current?.focus();
  }

  useEffect(() => {
    if (activeIdx >= 0 && listRef.current) {
      const item = listRef.current.children[activeIdx] as HTMLElement;
      item?.scrollIntoView({ block: "nearest" });
    }
  }, [activeIdx]);

  return (
    <div className="relative">
      <div className="relative">
        <svg
          className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40 pointer-events-none"
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round"
            d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
        </svg>
        {query && (
          <button
            onMouseDown={(e) => { e.preventDefault(); onQueryChange(""); inputRef.current?.focus(); }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60 transition-colors"
            aria-label="Clear search"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
        <input
          ref={inputRef}
          type="text"
          role="combobox"
          aria-expanded={dropdownVisible}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={activeIdx >= 0 ? `${listId}-${activeIdx}` : undefined}
          value={query}
          disabled={disabled}
          onChange={(e) => { onQueryChange(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? "Chargement…" : (placeholder ?? "Search an ingredient…")}
          className="
            w-full pl-10 pr-9 py-3 rounded-xl
            bg-white/10 border border-white/20 text-white placeholder-white/40
            focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent
            text-base transition-colors disabled:opacity-50 disabled:cursor-not-allowed
          "
        />
      </div>

      {dropdownVisible && (
        <ul
          id={listId}
          ref={listRef}
          role="listbox"
          className="
            absolute z-50 mt-1 w-full max-h-64 overflow-y-auto
            bg-brand-900 border border-white/20 rounded-xl shadow-2xl
          "
        >
          {suggestions.map((ing, idx) => (
            <li
              key={ing.id}
              id={`${listId}-${idx}`}
              role="option"
              aria-selected={idx === activeIdx}
              onMouseDown={() => commit(ing)}
              onMouseEnter={() => setActiveIdx(idx)}
              className={`
                px-4 py-2.5 cursor-pointer text-sm capitalize transition-colors
                ${idx === activeIdx ? "bg-brand-600 text-white" : "text-white/80 hover:bg-white/10"}
                ${idx < suggestions.length - 1 ? "border-b border-white/10" : ""}
              `}
            >
              {translate(ing.name)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
