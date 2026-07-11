import { useSyncExternalStore } from "react";

// Must stay identical to slugify() in pipeline/fetch_images.py — the slug is
// the join key between ingredient names and committed image files.
export function ingredientSlug(name: string): string {
  return name
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

const IMAGE_DIR = `${import.meta.env.BASE_URL}ingredient-images/`;

let available: Set<string> | null = null;
let started = false;
const listeners = new Set<() => void>();

function startManifestLoad() {
  if (started) return;
  started = true;
  fetch(`${IMAGE_DIR}manifest.json`)
    .then((r) => (r.ok ? r.json() : null))
    .then((data) => {
      if (data && Array.isArray(data.slugs)) {
        available = new Set<string>(data.slugs);
        listeners.forEach((l) => l());
      }
    })
    .catch(() => {
      // No manifest (images not generated yet) — emoji tiles remain.
    });
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

function getSnapshot() {
  return available;
}

export function useIngredientImageUrl(name: string): string | null {
  startManifestLoad();
  const slugs = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  if (!slugs) return null;
  const slug = ingredientSlug(name);
  return slugs.has(slug) ? `${IMAGE_DIR}${slug}.webp` : null;
}
