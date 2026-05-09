import { useState, useRef, useEffect, useId } from "react";
import type { Ingredient } from "../types";

interface Props {
  ingredients: Ingredient[];
  selectedIds: Set<number>;
  onSelect: (ingredient: Ingredient) => void;
  translate: (name: string) => string;
  placeholder?: string;
  disabled?: boolean;
}

const MAX_SUGGESTIONS = 8;

export default function SearchInput({ ingredients, selectedIds, onSelect, translate, placeholder, disabled }: Props) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listId = useId();

  const suggestions = query.length < 1
    ? []
    : ingredients
        .filter((i) => {
          if (selectedIds.has(i.id)) return false;
          const display = translate(i.name).toLowerCase();
          return display.includes(query.toLowerCase());
        })
        .sort((a, b) => {
          const aName = translate(a.name).toLowerCase();
          const bName = translate(b.name).toLowerCase();
          const q = query.toLowerCase();
          const aPrefix = aName.startsWith(q);
          const bPrefix = bName.startsWith(q);
          if (aPrefix !== bPrefix) return aPrefix ? -1 : 1;
          return b.freq - a.freq;
        })
        .slice(0, MAX_SUGGESTIONS);

  useEffect(() => {
    setActiveIdx(-1);
  }, [query]);

  // Reset query when language changes (translated query is no longer valid)
  useEffect(() => {
    setQuery("");
  }, [translate]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (!open || suggestions.length === 0) return;
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
    setQuery("");
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
        <input
          ref={inputRef}
          type="text"
          role="combobox"
          aria-expanded={open && suggestions.length > 0}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={activeIdx >= 0 ? `${listId}-${activeIdx}` : undefined}
          value={query}
          disabled={disabled}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? "Chargement…" : (placeholder ?? "Add an ingredient…")}
          className="
            w-full pl-10 pr-4 py-3 rounded-xl
            bg-white/10 border border-white/20 text-white placeholder-white/40
            focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent
            text-base transition-colors disabled:opacity-50 disabled:cursor-not-allowed
          "
        />
      </div>

      {open && suggestions.length > 0 && (
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
