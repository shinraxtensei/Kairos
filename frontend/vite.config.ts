import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": new URL("./src", import.meta.url).pathname } },
  // Built straight into the package FastAPI serves, so production stays one
  // process: no second runtime to deploy, monitor or keep in sync.
  build: { outDir: "../backend/kairos/static", emptyOutDir: true },
  server: {
    port: 5173,
    // Dev only. In production the API and the bundle share an origin.
    proxy: { "/api": "http://localhost:8000", "/health": "http://localhost:8000" },
  },
})
