import { useState, type ReactNode } from "react";
import { getIngredientEmoji, getIngredientColor } from "../utils/ingredientEmoji";
import { useIngredientImageUrl } from "../utils/ingredientImage";

// One backdrop shared by every photo tile (issue #48: similar background).
// Emoji fallback tiles keep their hash-derived colour.
const IMAGE_BG = "hsl(233, 23%, 22%)";

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

  return (
    <div
      className="relative w-full aspect-square flex items-center justify-center"
      style={{ background: showImage ? IMAGE_BG : getIngredientColor(name) }}
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
