import { defineConfig } from "vitest/config";
import type { PreviewServer, ViteDevServer } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import type { IncomingMessage, ServerResponse } from "node:http";
import path from "node:path";

const repoRoot = path.resolve(__dirname, "..");
const staticApiRoot = path.join(repoRoot, "public", "api");

function staticApiMiddleware() {
  const handler = (req: IncomingMessage, res: ServerResponse, next: () => void) => {
    const requestUrl = new URL(req.url || "/", "http://127.0.0.1");
    const relativePath = decodeURIComponent(requestUrl.pathname.replace(/^\/+/, "")) || "manifest.json";
    const target = path.resolve(staticApiRoot, relativePath);
    const boundary = path.relative(staticApiRoot, target);
    const insideStaticApi = boundary !== "" && !boundary.startsWith("..") && !path.isAbsolute(boundary);
    if (!insideStaticApi || !fs.existsSync(target) || !fs.statSync(target).isFile()) {
      next();
      return;
    }
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.setHeader("Cache-Control", "no-cache");
    fs.createReadStream(target).pipe(res);
  };
  return {
    name: "static-api-middleware",
    configureServer(server: ViteDevServer) {
      server.middlewares.use("/api", handler);
    },
    configurePreviewServer(server: PreviewServer) {
      server.middlewares.use("/api", handler);
    },
  };
}

export default defineConfig({
  plugins: [react(), staticApiMiddleware()],
  server: {
    port: 5174,
    proxy: {
      "/local-api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/local-api/, "/api"),
      },
    },
  },
  preview: {
    port: 4174,
  },
  test: {
    environment: "node",
    setupFiles: "./src/test/setup.ts",
  },
});
