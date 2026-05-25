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
      "/config": {
        target: API_HTTP,
        changeOrigin: true,
        // /config is BOTH a React route (live runtime editor at the
        // bare path) AND a REST endpoint (GET reads, POST writes).
        // We bypass to the SPA only on a browser navigation request
        // (Accept: text/html), so fetch() calls from the React app
        // — which use Accept: application/json or */* — still hit
        // the backend. URL discrimination alone (as the /operator
        // bypass does) would break the POST /config save round-trip.
        bypass: (req) => {
          if (req.url !== "/config" && req.url !== "/config/") return undefined;
          const accept = req.headers.accept ?? "";
          if (req.method === "GET" && accept.includes("text/html")) {
            return req.url;
          }
          return undefined;
        },
      },
      "/chain": API_HTTP,
      "/dashboard": API_HTTP,
      "/encrypted-heatmap": API_HTTP,
      "/coach": API_HTTP,
      "/pty": API_HTTP,
      "/dp": API_HTTP,
      "/agents": API_HTTP,
      "/world": API_HTTP,
      "/arena": API_HTTP,
      "/repl": API_HTTP,
      "/learning": API_HTTP,
      "/crypto": API_HTTP,
      "/defenses": API_HTTP,
      "/logistics": API_HTTP,
      "/federated": API_HTTP,
      "/benchmark": API_HTTP,
      "/events": API_HTTP,
      "/security": API_HTTP,
      "/attacks": API_HTTP,
      "/operator": {
        target: API_HTTP,
        changeOrigin: true,
        bypass: (req) => {
          if (req.url === "/operator" || req.url === "/operator/") return req.url;
          return undefined;
        },
      },
      "/ctf": API_HTTP,
      "/attacker": API_HTTP,
      "/export": API_HTTP,
      "/ws": { target: API_WS, ws: true },
    },
  },
  build: {
    target: "es2022",
    sourcemap: true,
  },
});
