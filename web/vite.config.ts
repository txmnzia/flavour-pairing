import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

const base = "/flavour-pairing/";

export default defineConfig({
  base,
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
        globIgnores: ["curate.html", "merge.html"],
        navigateFallbackDenylist: [/\/curate\.html$/, /\/merge\.html$/],
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
        ],
      },
    }),
  ],
});
