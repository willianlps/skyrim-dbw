import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Fixed port so Tauri can find the dev server.
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    // Rust builds inside src-tauri; Vite must not watch that folder.
    watch: {
      ignored: ["**/src-tauri/**"],
    },
  },
});
