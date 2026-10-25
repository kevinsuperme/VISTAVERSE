import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const rootDir = path.dirname(fileURLToPath(import.meta.url));

// Vite config: React + Tailwind, admin on 5174 with /api proxy
export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  // Production is mounted behind the main Nginx instance at /admin/;
  // development keeps the existing root path on port 5174.
  base: mode === "production" ? "/admin/" : "/",
  resolve: {
    alias: {
      "@": path.resolve(rootDir, "./src"),
    },
  },
  server: {
    port: 5174,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/static": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
}));
