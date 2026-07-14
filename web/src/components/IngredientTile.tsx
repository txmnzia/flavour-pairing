import { useState, type ReactNode } from "react";
import { getIngredientEmoji } from "../utils/ingredientEmoji";
import { useIngredientImageUrl } from "../utils/ingredientImage";
import { getIngredientCategory } from "../db";
import { categoryColor } from "../utils/categoryColor";

export default function IngredientTile({
  name,
  children,
}: {
  name: string;
  children?: ReactNode;
}) {
  const url = useIngredientImageUrl(name);
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const showImage = url !== null && url !== failedUrl;
  // Tile background tinted by ingredient category (photo and emoji alike).
  const bg = categoryColor(getIngredientCategory(name));

  return (
    <div
      className="relative w-full aspect-square flex items-center justify-center"
      style={{ background: bg }}
    >
      {showImage ? (
        <img
          src={url}
          alt={name}
          loading="lazy"
          draggable={false}
          className="w-full h-full object-contain p-2 select-none"
          onError={() => setFailedUrl(url)}
        />
      ) : (
        <span className="text-3xl select-none" role="img" aria-label={name}>
          {getIngredientEmoji(name)}
        </span>
      )}
      {children}
    </div>
  );
}
