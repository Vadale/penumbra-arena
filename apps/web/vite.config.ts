import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The Penumbra backend port is configurable via PENUMBRA_API_PORT
// so a dev whose port 8000 is occupied (another local service) can
// boot the API on 8100 and Vite still proxies cleanly.
// We avoid pulling @types/node into the workspace just to type
// process.env here — the cast is local to this config file.
declare const process: { env: Record<string, string | undefined> };
const API_PORT = process.env.PENUMBRA_API_PORT ?? "8000";
const API_HTTP = `http://localhost:${API_PORT}`;
const API_WS = `ws://localhost:${API_PORT}`;

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/health": API_HTTP,
      "/state": API_HTTP,
      "/control": API_HTTP,
      "/chain": API_HTTP,
      "/dashboard": API_HTTP,
      "/encrypted-heatmap": API_HTTP,
      "/coach": API_HTTP,
      "/pty": API_HTTP,
      "/dp": API_HTTP,
      "/agents": API_HTTP,
      "/world": API_HTTP,
      "/ws": { target: API_WS, ws: true },
    },
  },
  build: {
    target: "es2022",
    sourcemap: true,
  },
});
