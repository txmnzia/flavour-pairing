import type { Cuisine } from "../types";

interface Props {
  cuisines: Cuisine[];
  selected: Cuisine | null;
  onChange: (cuisine: Cuisine | null) => void;
}

export default function CuisineFilter({ cuisines, selected, onChange }: Props) {
  const allOption = cuisines.find((c) => c.name === "all");
  const namedCuisines = cuisines
    .filter((c) => c.name !== "all")
    .sort((a, b) => a.name.localeCompare(b.name));

  function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const id = Number(e.target.value);
    if (id === allOption?.id) {
      onChange(null);
    } else {
      onChange(cuisines.find((c) => c.id === id) ?? null);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <label htmlFor="cuisine-select" className="text-sm text-white/60 whitespace-nowrap">
        Cuisine
      </label>
      <select
        id="cuisine-select"
        value={selected?.id ?? allOption?.id ?? ""}
        onChange={handleChange}
        className="
          bg-white/10 border border-white/20 text-white text-sm rounded-lg
          px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-brand-400
          cursor-pointer appearance-none pr-8
          bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20fill%3D%22none%22%20viewBox%3D%220%200%2020%2020%22%3E%3Cpath%20stroke%3D%22%23fff%22%20stroke-opacity%3D%220.5%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%20stroke-width%3D%221.5%22%20d%3D%22M6%208l4%204%204-4%22%2F%3E%3C%2Fsvg%3E')]
          bg-no-repeat bg-[right_0.5rem_center] bg-[length:1.25rem]
        "
      >
        <option value={allOption?.id ?? ""} className="bg-brand-900 text-white">
          All cuisines
        </option>
        {namedCuisines.map((c) => (
          <option key={c.id} value={c.id} className="bg-brand-900 text-white">
            {c.name}
          </option>
        ))}
      </select>
    </div>
  );
}
