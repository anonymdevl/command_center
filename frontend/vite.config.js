import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Builds into the app's public folder, which Frappe already serves through the
 * assets symlink. Nothing here runs on the server: the built output is committed
 * and deployment stays `git pull` + `bench migrate` + `bench restart`.
 *
 * This file lives in frontend/, never at the app root. A package.json with a
 * build script at the app root makes `bench build` try to run it, which fails on
 * any server without Node -- the commonest way this arrangement bites people.
 */
export default defineConfig({
  plugins: [react()],
  base: "/assets/command_center/command-center/",
  build: {
    outDir: "../command_center/public/command-center",
    emptyOutDir: true,
    manifest: true,
    // Stable names: the Jinja template references them directly, so there is no
    // manifest lookup at request time and no chance of the page pointing at a
    // bundle that a rebuild renamed.
    rollupOptions: {
      output: {
        entryFileNames: "command-center.js",
        chunkFileNames: "[name].js",
        assetFileNames: (info) =>
          info.name && info.name.endsWith(".css")
            ? "command-center.css"
            : "[name][extname]",
      },
    },
  },
  server: {
    port: 8080,
    proxy: {
      // `npm run dev` talks to a real site, so the session cookie and every
      // endpoint behave exactly as they will in production.
      "^/(api|assets|files|private)": {
        target: process.env.CC_SITE || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
