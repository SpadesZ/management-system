// File Path: frontend/vite.config.ts
// Timestamp: 2026-05-25T12:00:00+08:00
// Version: v0.1

import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    host: "0.0.0.0",
    port: 5173,
  },
});
