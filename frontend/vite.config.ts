import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

const PAGE_EXTENSIONS = ["", ".tsx", ".ts", ".jsx", ".js", "/index.tsx", "/index.ts"];

/**
 * Let the bundle build even while the `pages/admin` and `pages/contacts`
 * screens are still being written: an unresolvable page import becomes a stub
 * whose empty default export makes `routes.tsx` render its "coming soon"
 * placeholder instead of failing the build.
 */
function optionalPages(): Plugin {
  const VIRTUAL = "\0chattysup:missing-page";
  return {
    name: "chattysup-optional-pages",
    resolveId(source, importer) {
      if (!importer || !/^\.\/pages\/(admin|contacts)\//.test(source)) return null;
      const target = path.resolve(path.dirname(importer), source);
      const exists = PAGE_EXTENSIONS.some((extension) =>
        fs.existsSync(`${target}${extension}`),
      );
      return exists ? null : VIRTUAL;
    },
    load(id) {
      return id === VIRTUAL ? "export default null;" : null;
    },
  };
}

/**
 * The production bundle is emitted straight into the FastAPI static directory
 * so a single `uvicorn app.main:app` serves both the API and the SPA.
 */
export default defineConfig({
  plugins: [react(), optionalPages()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    outDir: "../backend/app/static",
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
