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
    // Content-hashed names. A stable filename meant a browser kept serving the
    // previous bundle after a deploy, which is indistinguishable from a fix that
    // did not work -- and cost several rounds of chasing symptoms that were
    // already fixed on the server. The page reads the manifest, so the URL
    // changes whenever the content does and no one has to remember to
    // hard-refresh.
    rollupOptions: {
      output: {
        entryFileNames: "command-center.[hash].js",
        chunkFileNames: "[name].[hash].js",
        assetFileNames: "[name].[hash][extname]",
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
