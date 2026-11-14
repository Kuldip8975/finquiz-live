import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the Vite server forwards socket traffic to Flask on :5000,
// so the browser talks to one address. `host: true` lets phones on the same
// Wi-Fi open the dev server for testing.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/socket.io": { target: process.env.API_PROXY ?? "http://localhost:5000", ws: true },
    },
  },
});
