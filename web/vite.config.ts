import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import { execSync } from "node:child_process";

const base = "/flavour-pairing/";

// Human-readable build id shown in the FAQ so the deployed version is
// identifiable (e.g. to confirm the service worker picked up a new build).
// GITHUB_SHA is set in CI; falls back to local git, then "dev".
function buildId(): string {
  let sha = process.env.GITHUB_SHA?.slice(0, 7);
  if (!sha) {
    try { sha = execSync("git rev-parse --short HEAD").toString().trim(); }
    catch { sha = "dev"; }
  }
  const date = new Date().toISOString().slice(0, 10);
  return `${date} · ${sha}`;
}

export default defineConfig({
  base,
  define: {
    __BUILD_ID__: JSON.stringify(buildId()),
  },
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["pairings.json", "icons/*.png"],
      manifest: {
        name: "Flavour Pairing",
        short_name: "Flavour",
        description: "Discover ingredient pairings based on recipe co-occurrence",
        theme_color: "#1a1a2e",
        background_color: "#1a1a2e",
        display: "standalone",
        start_url: base,
        icons: [
          { src: "icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any maskable" },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html}"],
        globIgnores: ["curate.html", "merge.html", "annotate.html", "images.html", "attributions.html", "ingredient-images/**"],
        navigateFallbackDenylist: [/\/curate\.html$/, /\/merge\.html$/, /\/annotate\.html$/, /\/images\.html$/, /\/attributions\.html$/],
        runtimeCaching: [
          {
            urlPattern: /pairings\.json$/,
            handler: "NetworkFirst",
            options: {
              cacheName: "pairings-data",
              expiration: { maxEntries: 1, maxAgeSeconds: 60 * 60 * 24 * 7 },
              networkTimeoutSeconds: 5,
            },
          },
          {
            urlPattern: /ingredient-images\/manifest\.json$/,
            handler: "StaleWhileRevalidate",
            options: {
              cacheName: "ingredient-images-manifest",
              expiration: { maxEntries: 1, maxAgeSeconds: 60 * 60 * 24 * 30 },
            },
          },
          {
            urlPattern: /ingredient-images\/.*\.webp$/,
            handler: "CacheFirst",
            options: {
              cacheName: "ingredient-images",
              expiration: { maxEntries: 600, maxAgeSeconds: 60 * 60 * 24 * 90 },
            },
          },
        ],
      },
    }),
  ],
});
