import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Relative base so the built app works at any path (root of a CDN, a subpath,
  // etc.). Assets are referenced relative to index.html.
  base: "./",
  // Output to ./build (Vite defaults to ./dist). Either works; the deploy
  // script uploads whichever exists.
  build: {
    outDir: "build",
  },
  server: {
    host: true,
    port: 5173,
    // Proxy API + WebSocket to the backend in dev so the browser only ever
    // talks to this (5173) origin — no CORS needed locally.
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/ws": { target: "ws://localhost:8000", ws: true, changeOrigin: true },
    },
  },
});
